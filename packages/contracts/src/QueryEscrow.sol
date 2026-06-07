// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./AgentRegistry.sol";
import "./ReputationManager.sol";
import "./DecisionLedger.sol";

contract QueryEscrow is Ownable, ReentrancyGuard {
    AgentRegistry public registry;
    ReputationManager public reputation;
    DecisionLedger public ledger;

    address public orchestratorAddress;

    enum QueryStatus { Open, Collecting, Scoring, Escalating, Resolved, Failed }

    struct Query {
        uint256 id;
        address requester;
        bytes32 questionHash;
        string[] capabilities;
        uint256 bounty;
        uint256 deadline;
        QueryStatus status;
        address winner;
        uint8 round;
        uint256 createdAt;
    }

    struct Response {
        address agent;
        bytes32 responseHash;
        uint256 submittedAt;
        uint8 round;
    }

    mapping(uint256 => Query) public queries;
    mapping(uint256 => Response[]) public responses;
    mapping(uint256 => mapping(address => bool)) public hasResponded;

    uint256 public queryCount;
    uint256 public constant ESCALATION_BOUNTY_INCREASE = 20; // 20%

    event QueryCreated(
        uint256 indexed queryId,
        address indexed requester,
        bytes32 questionHash,
        string[] capabilities,
        uint256 bounty,
        uint256 deadline
    );
    event ResponseSubmitted(
        uint256 indexed queryId,
        address indexed agent,
        bytes32 responseHash,
        uint8 round
    );
    event WinnerSelected(
        uint256 indexed queryId,
        address indexed winner,
        uint256 bounty,
        bytes32 memoryHash,
        uint8 round
    );
    event QueryEscalated(uint256 indexed queryId, uint8 newRound, uint256 newBounty);
    event QueryExpired(uint256 indexed queryId, address requester, uint256 refund);
    event StatusChanged(uint256 indexed queryId, QueryStatus newStatus);

    modifier onlyOrchestrator() {
        require(
            msg.sender == owner() || msg.sender == orchestratorAddress,
            "QueryEscrow: not orchestrator"
        );
        _;
    }

    constructor(
        address _registry,
        address _reputation,
        address _ledger
    ) Ownable(msg.sender) {
        registry = AgentRegistry(_registry);
        reputation = ReputationManager(_reputation);
        ledger = DecisionLedger(_ledger);
        orchestratorAddress = msg.sender;
    }

    function setOrchestratorAddress(address _orchestrator) external onlyOwner {
        orchestratorAddress = _orchestrator;
    }

    function createQuery(
        string[] calldata capabilities,
        bytes32 questionHash,
        uint256 deadline
    ) external payable returns (uint256 queryId) {
        require(msg.value > 0, "QueryEscrow: bounty required");
        require(capabilities.length > 0, "QueryEscrow: capabilities required");
        require(deadline > block.timestamp, "QueryEscrow: invalid deadline");

        queryId = ++queryCount;
        queries[queryId] = Query({
            id: queryId,
            requester: msg.sender,
            questionHash: questionHash,
            capabilities: capabilities,
            bounty: msg.value,
            deadline: deadline,
            status: QueryStatus.Open,
            winner: address(0),
            round: 1,
            createdAt: block.timestamp
        });

        emit QueryCreated(queryId, msg.sender, questionHash, capabilities, msg.value, deadline);
    }

    function updateStatus(uint256 queryId, QueryStatus newStatus) external onlyOrchestrator {
        queries[queryId].status = newStatus;
        emit StatusChanged(queryId, newStatus);
    }

    function submitResponse(
        uint256 queryId,
        bytes32 responseHash
    ) external {
        Query storage q = queries[queryId];
        require(q.id != 0, "QueryEscrow: query not found");
        require(
            q.status == QueryStatus.Open ||
            q.status == QueryStatus.Collecting ||
            q.status == QueryStatus.Escalating,
            "QueryEscrow: not collecting"
        );
        require(!hasResponded[queryId][msg.sender], "QueryEscrow: already responded this round");
        require(block.timestamp < q.deadline, "QueryEscrow: deadline passed");
        require(registry.isActive(msg.sender), "QueryEscrow: agent not registered");

        responses[queryId].push(Response({
            agent: msg.sender,
            responseHash: responseHash,
            submittedAt: block.timestamp,
            round: q.round
        }));
        hasResponded[queryId][msg.sender] = true;

        emit ResponseSubmitted(queryId, msg.sender, responseHash, q.round);
    }

    function selectWinner(
        uint256 queryId,
        address winner,
        bytes32 memoryHash
    ) external onlyOrchestrator nonReentrant {
        Query storage q = queries[queryId];
        require(q.id != 0, "QueryEscrow: not found");
        require(
            q.status == QueryStatus.Collecting ||
            q.status == QueryStatus.Scoring ||
            q.status == QueryStatus.Open ||
            q.status == QueryStatus.Escalating,
            "QueryEscrow: invalid status"
        );
        require(winner != address(0), "QueryEscrow: invalid winner");

        q.winner = winner;
        q.status = QueryStatus.Resolved;

        // Update reputation for all respondents in current round
        Response[] storage resps = responses[queryId];
        for (uint256 i = 0; i < resps.length; i++) {
            if (resps[i].round == q.round) {
                if (resps[i].agent == winner) {
                    reputation.recordWin(resps[i].agent);
                } else {
                    reputation.recordLoss(resps[i].agent);
                }
            }
        }

        // Anchor memory hash on-chain
        ledger.anchor(queryId, memoryHash, q.round, winner);

        // Pay winner
        uint256 bounty = q.bounty;
        q.bounty = 0;
        payable(winner).transfer(bounty);

        emit WinnerSelected(queryId, winner, bounty, memoryHash, q.round);
    }

    function escalate(uint256 queryId) external onlyOrchestrator {
        Query storage q = queries[queryId];
        require(q.id != 0, "QueryEscrow: not found");
        require(
            q.status == QueryStatus.Scoring || q.status == QueryStatus.Collecting,
            "QueryEscrow: invalid status"
        );

        uint8 prevRound = q.round;
        q.round++;
        q.status = QueryStatus.Escalating;
        q.deadline = block.timestamp + 5 minutes;

        // Reset per-agent response tracking for new round
        Response[] storage resps = responses[queryId];
        for (uint256 i = 0; i < resps.length; i++) {
            if (resps[i].round == prevRound) {
                hasResponded[queryId][resps[i].agent] = false;
            }
        }

        emit QueryEscalated(queryId, q.round, q.bounty);
    }

    function addBounty(uint256 queryId) external payable {
        require(queries[queryId].id != 0, "QueryEscrow: not found");
        require(
            queries[queryId].status == QueryStatus.Escalating,
            "QueryEscrow: not escalating"
        );
        queries[queryId].bounty += msg.value;
    }

    function expireQuery(uint256 queryId) external nonReentrant {
        Query storage q = queries[queryId];
        require(q.id != 0, "QueryEscrow: not found");
        require(block.timestamp >= q.deadline, "QueryEscrow: not expired");
        require(
            q.status != QueryStatus.Resolved && q.status != QueryStatus.Failed,
            "QueryEscrow: already finalized"
        );

        q.status = QueryStatus.Failed;
        uint256 refund = q.bounty;
        q.bounty = 0;
        payable(q.requester).transfer(refund);

        emit QueryExpired(queryId, q.requester, refund);
    }

    function getQuery(uint256 queryId) external view returns (Query memory) {
        return queries[queryId];
    }

    function getResponses(uint256 queryId) external view returns (Response[] memory) {
        return responses[queryId];
    }

    function getResponsesForRound(uint256 queryId, uint8 round) external view returns (Response[] memory) {
        Response[] storage all = responses[queryId];
        uint256 count = 0;
        for (uint256 i = 0; i < all.length; i++) {
            if (all[i].round == round) count++;
        }
        Response[] memory result = new Response[](count);
        uint256 j = 0;
        for (uint256 i = 0; i < all.length; i++) {
            if (all[i].round == round) result[j++] = all[i];
        }
        return result;
    }
}
