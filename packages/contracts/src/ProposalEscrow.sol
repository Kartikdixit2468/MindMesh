// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./ReputationManager.sol";

/**
 * @title ProposalEscrow
 * @notice Manages proposal-track tasks: idea evaluation, team formation,
 *         multi-agent discussion, and reward distribution on Monad.
 *
 * Flow:
 *   createProposal (locks MON bounty)
 *     → formTeam    (records team on-chain)
 *     → settleProposal (distributes rewards, anchors report hash)
 *   or
 *     → expireProposal (refunds requester if no team formed)
 */
contract ProposalEscrow is Ownable, ReentrancyGuard {
    ReputationManager public reputation;
    address public orchestratorAddress;

    enum ProposalStatus {
        Open,
        TeamFormed,
        Discussing,
        Settled,
        Failed
    }

    struct TeamMember {
        address agent;
        string role;
    }

    struct Proposal {
        uint256 id;
        address requester;
        bytes32 descriptionHash;   // keccak256 of full description
        uint256 bounty;            // wei locked
        uint256 maxRoles;
        uint256 deadline;
        ProposalStatus status;
        bytes32 reportHash;        // SHA256 of final report, set at settlement
        string reportIpfsCid;      // IPFS CID of final report
        uint256 createdAt;
    }

    uint256 public nextProposalId;
    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => TeamMember[]) public proposalTeams;

    // Reputation deltas
    uint256 public constant WIN_BONUS = 150;
    uint256 public constant PARTICIPATION_BONUS = 50;

    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed requester,
        bytes32 descriptionHash,
        uint256 bounty,
        uint256 maxRoles,
        uint256 deadline
    );

    event TeamFormed(
        uint256 indexed proposalId,
        address[] agents,
        string[] roles
    );

    event ProposalSettled(
        uint256 indexed proposalId,
        bytes32 reportHash,
        string reportIpfsCid,
        address[] contributors,
        uint256[] shares
    );

    event ProposalFailed(uint256 indexed proposalId, string reason);

    // Events for off-chain data anchored on-chain via calldata
    event RolesAnnounced(uint256 indexed proposalId, string[] names, string[] descriptions);
    event BidPosted(uint256 indexed proposalId, string roleName, address indexed agent, uint256 fitScore100, string reasoning);
    event MessagePosted(uint256 indexed proposalId, uint256 indexed roundNum, address indexed agent, string role, string content, string roundType);
    event StatusUpdated(uint256 indexed proposalId, string newStatus);

    modifier onlyOrchestrator() {
        require(
            msg.sender == orchestratorAddress || msg.sender == owner(),
            "ProposalEscrow: caller is not the orchestrator"
        );
        _;
    }

    constructor(address _reputation) Ownable(msg.sender) {
        reputation = ReputationManager(_reputation);
    }

    function setOrchestrator(address _orchestrator) external onlyOwner {
        orchestratorAddress = _orchestrator;
    }

    // ── Create ────────────────────────────────────────────────────────────────

    /**
     * @notice Submit a proposal and lock a MON bounty.
     * @param descriptionHash keccak256 of the full proposal text
     * @param maxRoles Maximum number of agent roles for this proposal
     * @param deadlineSeconds Seconds from now until proposal expires
     */
    function createProposal(
        bytes32 descriptionHash,
        uint256 maxRoles,
        uint256 deadlineSeconds
    ) external payable returns (uint256 proposalId) {
        require(maxRoles >= 2 && maxRoles <= 8, "ProposalEscrow: maxRoles must be 2-8");
        require(deadlineSeconds >= 60, "ProposalEscrow: deadline must be at least 60s");

        proposalId = nextProposalId++;
        proposals[proposalId] = Proposal({
            id: proposalId,
            requester: msg.sender,
            descriptionHash: descriptionHash,
            bounty: msg.value,
            maxRoles: maxRoles,
            deadline: block.timestamp + deadlineSeconds,
            status: ProposalStatus.Open,
            reportHash: bytes32(0),
            reportIpfsCid: "",
            createdAt: block.timestamp
        });

        emit ProposalCreated(
            proposalId,
            msg.sender,
            descriptionHash,
            msg.value,
            maxRoles,
            block.timestamp + deadlineSeconds
        );
    }

    // ── Team Formation ────────────────────────────────────────────────────────

    /**
     * @notice Record team formation on-chain. Called by orchestrator after bidding.
     */
    function formTeam(
        uint256 proposalId,
        address[] calldata agents,
        string[] calldata roles
    ) external onlyOrchestrator {
        Proposal storage p = proposals[proposalId];
        require(p.status == ProposalStatus.Open, "ProposalEscrow: proposal not open");
        require(agents.length == roles.length, "ProposalEscrow: agents/roles length mismatch");
        require(agents.length >= 2, "ProposalEscrow: need at least 2 agents");
        require(block.timestamp < p.deadline, "ProposalEscrow: deadline passed");

        delete proposalTeams[proposalId];
        for (uint256 i = 0; i < agents.length; i++) {
            proposalTeams[proposalId].push(TeamMember({ agent: agents[i], role: roles[i] }));
        }

        p.status = ProposalStatus.TeamFormed;

        emit TeamFormed(proposalId, agents, roles);
    }

    // ── Settlement ────────────────────────────────────────────────────────────

    /**
     * @notice Settle a proposal: distribute bounty proportionally, anchor report hash.
     * @param proposalId The proposal to settle
     * @param reportHash SHA256 of the final Markdown report (as bytes32)
     * @param reportIpfsCid IPFS CID string where the full report is stored
     * @param contributors Agent addresses receiving rewards
     * @param shares Basis points (out of 10000) for each contributor's share
     */
    function settleProposal(
        uint256 proposalId,
        bytes32 reportHash,
        string calldata reportIpfsCid,
        address[] calldata contributors,
        uint256[] calldata shares
    ) external onlyOrchestrator nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(
            p.status == ProposalStatus.TeamFormed || p.status == ProposalStatus.Discussing,
            "ProposalEscrow: invalid status for settlement"
        );
        require(contributors.length == shares.length, "ProposalEscrow: contributors/shares mismatch");

        // Validate shares sum to 10000
        uint256 totalShares;
        for (uint256 i = 0; i < shares.length; i++) {
            totalShares += shares[i];
        }
        require(totalShares == 10000, "ProposalEscrow: shares must sum to 10000");

        p.status = ProposalStatus.Settled;
        p.reportHash = reportHash;
        p.reportIpfsCid = reportIpfsCid;

        // Distribute bounty
        uint256 bounty = p.bounty;
        for (uint256 i = 0; i < contributors.length; i++) {
            uint256 amount = (bounty * shares[i]) / 10000;
            if (amount > 0) {
                (bool ok, ) = contributors[i].call{value: amount}("");
                require(ok, "ProposalEscrow: transfer failed");
            }

            // Update on-chain reputation
            try reputation.recordWin(contributors[i]) {} catch {}
        }

        emit ProposalSettled(proposalId, reportHash, reportIpfsCid, contributors, shares);
    }

    // ── Failure ───────────────────────────────────────────────────────────────

    /**
     * @notice Mark proposal as failed and refund the requester.
     */
    function failProposal(uint256 proposalId, string calldata reason)
        external
        onlyOrchestrator
        nonReentrant
    {
        Proposal storage p = proposals[proposalId];
        require(
            p.status == ProposalStatus.Open || p.status == ProposalStatus.TeamFormed,
            "ProposalEscrow: cannot fail settled proposal"
        );

        p.status = ProposalStatus.Failed;

        if (p.bounty > 0) {
            (bool ok, ) = p.requester.call{value: p.bounty}("");
            require(ok, "ProposalEscrow: refund failed");
        }

        emit ProposalFailed(proposalId, reason);
    }

    // ── Views ─────────────────────────────────────────────────────────────────

    function getTeam(uint256 proposalId)
        external
        view
        returns (address[] memory agents, string[] memory roles)
    {
        TeamMember[] storage team = proposalTeams[proposalId];
        agents = new address[](team.length);
        roles = new string[](team.length);
        for (uint256 i = 0; i < team.length; i++) {
            agents[i] = team[i].agent;
            roles[i] = team[i].role;
        }
    }

    function getProposal(uint256 proposalId) external view returns (Proposal memory) {
        return proposals[proposalId];
    }

    // ── Calldata-only event emitters (no storage writes = cheap) ─────────────────

    function announceRoles(
        uint256 proposalId,
        string[] calldata names,
        string[] calldata descriptions
    ) external onlyOrchestrator {
        emit RolesAnnounced(proposalId, names, descriptions);
    }

    function postBid(
        uint256 proposalId,
        string calldata roleName,
        address agent,
        uint256 fitScore100,
        string calldata reasoning
    ) external onlyOrchestrator {
        emit BidPosted(proposalId, roleName, agent, fitScore100, reasoning);
    }

    function postMessage(
        uint256 proposalId,
        uint256 roundNum,
        address agent,
        string calldata role,
        string calldata content,
        string calldata roundType
    ) external onlyOrchestrator {
        emit MessagePosted(proposalId, roundNum, agent, role, content, roundType);
    }

    function updateStatus(uint256 proposalId, string calldata newStatus) external onlyOrchestrator {
        emit StatusUpdated(proposalId, newStatus);
    }
}
