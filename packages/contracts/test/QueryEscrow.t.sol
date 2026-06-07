// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/QueryEscrow.sol";
import "../src/AgentRegistry.sol";
import "../src/StakeVault.sol";
import "../src/ReputationManager.sol";
import "../src/DecisionLedger.sol";

contract QueryEscrowTest is Test {
    StakeVault public stakeVault;
    ReputationManager public reputationManager;
    DecisionLedger public ledger;
    AgentRegistry public registry;
    QueryEscrow public escrow;

    address public deployer = address(0xDEAD);
    address public requester = address(0xAAAA);
    address public agent1 = address(0x1111);
    address public agent2 = address(0x2222);

    uint256 public constant MIN_STAKE = 0.01 ether;
    uint256 public constant BOUNTY = 0.1 ether;

    function setUp() public {
        vm.startPrank(deployer);

        stakeVault = new StakeVault();
        reputationManager = new ReputationManager();
        ledger = new DecisionLedger();
        registry = new AgentRegistry(address(stakeVault), address(reputationManager));
        escrow = new QueryEscrow(address(registry), address(reputationManager), address(ledger));

        // Wire up contracts
        stakeVault.setRegistryContract(address(registry));
        reputationManager.setEscrowContract(address(escrow));
        ledger.setEscrowContract(address(escrow));
        escrow.setOrchestratorAddress(deployer);

        vm.stopPrank();

        vm.deal(deployer, 100 ether);
        vm.deal(requester, 100 ether);
        vm.deal(agent1, 10 ether);
        vm.deal(agent2, 10 ether);

        // Register agents (registry calls reputationManager.initializeAgent which requires escrowContract == registry)
        // But reputationManager.escrowContract is set to escrow. We need to handle this.
        // Solution: temporarily set escrowContract to registry for init, then back to escrow
        // Better: set escrowContract to registry so agents can be initialized during registration
        vm.prank(deployer);
        reputationManager.setEscrowContract(address(registry));

        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");
        vm.prank(agent2);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta2");

        // Now set escrowContract back to escrow
        vm.prank(deployer);
        reputationManager.setEscrowContract(address(escrow));
    }

    // ---- createQuery Tests ----

    function test_CreateQuery() public {
        bytes32 qHash = keccak256("What is the best DeFi protocol?");
        string[] memory caps = new string[](1);
        caps[0] = "nlp";
        uint256 deadline = block.timestamp + 1 hours;

        vm.prank(requester);
        uint256 qId = escrow.createQuery{value: BOUNTY}(caps, qHash, deadline);

        assertEq(qId, 1);
        QueryEscrow.Query memory q = escrow.getQuery(qId);
        assertEq(q.requester, requester);
        assertEq(q.bounty, BOUNTY);
        assertEq(q.deadline, deadline);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Open));
        assertEq(q.round, 1);
    }

    function test_CreateQuery_NoBounty() public {
        bytes32 qHash = keccak256("test");
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(requester);
        vm.expectRevert("QueryEscrow: bounty required");
        escrow.createQuery{value: 0}(caps, qHash, block.timestamp + 1 hours);
    }

    function test_CreateQuery_NoCapabilities() public {
        string[] memory caps = new string[](0);

        vm.prank(requester);
        vm.expectRevert("QueryEscrow: capabilities required");
        escrow.createQuery{value: BOUNTY}(caps, keccak256("test"), block.timestamp + 1 hours);
    }

    function test_CreateQuery_PastDeadline() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(requester);
        vm.expectRevert("QueryEscrow: invalid deadline");
        escrow.createQuery{value: BOUNTY}(caps, keccak256("test"), block.timestamp - 1);
    }

    function test_CreateQuery_IncrementsCount() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.startPrank(requester);
        escrow.createQuery{value: BOUNTY}(caps, keccak256("q1"), block.timestamp + 1 hours);
        escrow.createQuery{value: BOUNTY}(caps, keccak256("q2"), block.timestamp + 1 hours);
        vm.stopPrank();

        assertEq(escrow.queryCount(), 2);
    }

    // ---- submitResponse Tests ----

    function test_SubmitResponse() public {
        uint256 qId = _createQuery();

        bytes32 rHash = keccak256("My answer");
        vm.prank(agent1);
        escrow.submitResponse(qId, rHash);

        QueryEscrow.Response[] memory resps = escrow.getResponses(qId);
        assertEq(resps.length, 1);
        assertEq(resps[0].agent, agent1);
        assertEq(resps[0].responseHash, rHash);
        assertEq(resps[0].round, 1);
    }

    function test_SubmitResponse_TwoAgents() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Answer from agent1"));
        vm.prank(agent2);
        escrow.submitResponse(qId, keccak256("Answer from agent2"));

        QueryEscrow.Response[] memory resps = escrow.getResponses(qId);
        assertEq(resps.length, 2);
    }

    function test_SubmitResponse_AlreadyResponded() public {
        uint256 qId = _createQuery();

        vm.startPrank(agent1);
        escrow.submitResponse(qId, keccak256("Answer 1"));
        vm.expectRevert("QueryEscrow: already responded this round");
        escrow.submitResponse(qId, keccak256("Answer 2"));
        vm.stopPrank();
    }

    function test_SubmitResponse_UnregisteredAgent() public {
        uint256 qId = _createQuery();
        address unregistered = address(0x9999);

        vm.prank(unregistered);
        vm.expectRevert("QueryEscrow: agent not registered");
        escrow.submitResponse(qId, keccak256("Fake answer"));
    }

    function test_SubmitResponse_AfterDeadline() public {
        uint256 qId = _createQuery();

        // Move past deadline
        vm.warp(block.timestamp + 2 hours);

        vm.prank(agent1);
        vm.expectRevert("QueryEscrow: deadline passed");
        escrow.submitResponse(qId, keccak256("Late answer"));
    }

    function test_SubmitResponse_QueryNotFound() public {
        vm.prank(agent1);
        vm.expectRevert("QueryEscrow: query not found");
        escrow.submitResponse(999, keccak256("answer"));
    }

    // ---- selectWinner Tests ----

    function test_SelectWinner_WinnerGetsPaid() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Best answer"));

        uint256 balanceBefore = agent1.balance;
        bytes32 memHash = keccak256("memory_anchor_1");

        vm.prank(deployer);
        escrow.selectWinner(qId, agent1, memHash);

        uint256 balanceAfter = agent1.balance;
        assertEq(balanceAfter - balanceBefore, BOUNTY);
    }

    function test_SelectWinner_QueryResolved() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Answer"));

        vm.prank(deployer);
        escrow.selectWinner(qId, agent1, keccak256("mem"));

        QueryEscrow.Query memory q = escrow.getQuery(qId);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Resolved));
        assertEq(q.winner, agent1);
        assertEq(q.bounty, 0);
    }

    function test_SelectWinner_ReputationUpdated() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Good answer"));
        vm.prank(agent2);
        escrow.submitResponse(qId, keccak256("Bad answer"));

        vm.prank(deployer);
        escrow.selectWinner(qId, agent1, keccak256("mem"));

        uint256 agent1Score = reputationManager.getScore(agent1);
        uint256 agent2Score = reputationManager.getScore(agent2);

        assertEq(agent1Score, reputationManager.INITIAL_SCORE() + reputationManager.WIN_BONUS());
        assertEq(agent2Score, reputationManager.INITIAL_SCORE() - reputationManager.LOSS_PENALTY());
    }

    function test_SelectWinner_MemoryAnchored() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Answer"));

        bytes32 memHash = keccak256("important_memory");
        vm.prank(deployer);
        escrow.selectWinner(qId, agent1, memHash);

        bool verified = ledger.verifyMemory(qId, memHash);
        assertTrue(verified);
    }

    function test_SelectWinner_OnlyOrchestrator() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Answer"));

        vm.prank(agent2);
        vm.expectRevert("QueryEscrow: not orchestrator");
        escrow.selectWinner(qId, agent1, keccak256("mem"));
    }

    function test_SelectWinner_ZeroWinner() public {
        uint256 qId = _createQuery();

        vm.prank(deployer);
        vm.expectRevert("QueryEscrow: invalid winner");
        escrow.selectWinner(qId, address(0), keccak256("mem"));
    }

    // ---- expireQuery Tests ----

    function test_ExpireQuery_Refund() public {
        uint256 qId = _createQuery();

        uint256 balanceBefore = requester.balance;

        // Move past deadline
        vm.warp(block.timestamp + 2 hours);

        escrow.expireQuery(qId);

        uint256 balanceAfter = requester.balance;
        assertEq(balanceAfter - balanceBefore, BOUNTY);
    }

    function test_ExpireQuery_StatusFailed() public {
        uint256 qId = _createQuery();

        vm.warp(block.timestamp + 2 hours);
        escrow.expireQuery(qId);

        QueryEscrow.Query memory q = escrow.getQuery(qId);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Failed));
        assertEq(q.bounty, 0);
    }

    function test_ExpireQuery_NotExpiredYet() public {
        uint256 qId = _createQuery();

        vm.expectRevert("QueryEscrow: not expired");
        escrow.expireQuery(qId);
    }

    function test_ExpireQuery_AlreadyResolved() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Answer"));

        vm.prank(deployer);
        escrow.selectWinner(qId, agent1, keccak256("mem"));

        vm.warp(block.timestamp + 2 hours);
        vm.expectRevert("QueryEscrow: already finalized");
        escrow.expireQuery(qId);
    }

    // ---- updateStatus Tests ----

    function test_UpdateStatus() public {
        uint256 qId = _createQuery();

        vm.prank(deployer);
        escrow.updateStatus(qId, QueryEscrow.QueryStatus.Collecting);

        QueryEscrow.Query memory q = escrow.getQuery(qId);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Collecting));
    }

    function test_UpdateStatus_NotOrchestrator() public {
        uint256 qId = _createQuery();

        vm.prank(requester);
        vm.expectRevert("QueryEscrow: not orchestrator");
        escrow.updateStatus(qId, QueryEscrow.QueryStatus.Collecting);
    }

    // ---- getResponsesForRound Tests ----

    function test_GetResponsesForRound() public {
        uint256 qId = _createQuery();

        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Round 1 answer"));
        vm.prank(agent2);
        escrow.submitResponse(qId, keccak256("Round 1 answer 2"));

        QueryEscrow.Response[] memory round1 = escrow.getResponsesForRound(qId, 1);
        assertEq(round1.length, 2);
    }

    // ---- Helper ----

    function _createQuery() internal returns (uint256) {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";
        bytes32 qHash = keccak256("What is the best DeFi protocol?");
        uint256 deadline = block.timestamp + 1 hours;

        vm.prank(requester);
        return escrow.createQuery{value: BOUNTY}(caps, qHash, deadline);
    }
}
