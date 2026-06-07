// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/QueryEscrow.sol";
import "../src/AgentRegistry.sol";
import "../src/StakeVault.sol";
import "../src/ReputationManager.sol";
import "../src/DecisionLedger.sol";

/// @title Integration test: full end-to-end MonadBlitz flow
contract IntegrationTest is Test {
    StakeVault public stakeVault;
    ReputationManager public reputationManager;
    DecisionLedger public ledger;
    AgentRegistry public registry;
    QueryEscrow public escrow;

    address public deployer = address(0xDEAD);
    address public requester = address(0xAAAA);
    address public agent1 = address(0x1111);
    address public agent2 = address(0x2222);
    address public agent3 = address(0x3333);

    uint256 public constant STAKE = 0.01 ether;
    uint256 public constant BOUNTY = 1 ether;

    event QueryCreated(
        uint256 indexed queryId,
        address indexed requester,
        bytes32 questionHash,
        string[] capabilities,
        uint256 bounty,
        uint256 deadline
    );

    function setUp() public {
        // Fund all actors
        vm.deal(deployer, 100 ether);
        vm.deal(requester, 100 ether);
        vm.deal(agent1, 10 ether);
        vm.deal(agent2, 10 ether);
        vm.deal(agent3, 10 ether);

        vm.startPrank(deployer);

        // Step 1: Deploy all contracts in correct order
        stakeVault = new StakeVault();
        reputationManager = new ReputationManager();
        ledger = new DecisionLedger();
        registry = new AgentRegistry(address(stakeVault), address(reputationManager));
        escrow = new QueryEscrow(address(registry), address(reputationManager), address(ledger));

        // Step 2: Wire up contracts
        stakeVault.setRegistryContract(address(registry));
        ledger.setEscrowContract(address(escrow));
        escrow.setOrchestratorAddress(deployer);

        // Set reputation escrow to registry for agent initialization phase
        reputationManager.setEscrowContract(address(registry));

        vm.stopPrank();

        // Step 3: Register 3 agents
        string[] memory caps1 = new string[](2);
        caps1[0] = "nlp";
        caps1[1] = "reasoning";

        string[] memory caps2 = new string[](2);
        caps2[0] = "nlp";
        caps2[1] = "code";

        string[] memory caps3 = new string[](1);
        caps3[0] = "vision";

        vm.prank(agent1);
        registry.register{value: STAKE}(caps1, "ipfs://agent1");

        vm.prank(agent2);
        registry.register{value: STAKE}(caps2, "ipfs://agent2");

        vm.prank(agent3);
        registry.register{value: STAKE}(caps3, "ipfs://agent3");

        // Step 4: Switch reputation escrow back to QueryEscrow
        vm.prank(deployer);
        reputationManager.setEscrowContract(address(escrow));
    }

    function test_EndToEnd_TwoAgentsRespond_WinnerPaid() public {
        // Verify initial setup
        assertEq(registry.getActiveAgents().length, 3);
        assertEq(stakeVault.getStake(agent1), STAKE);
        assertEq(stakeVault.getStake(agent2), STAKE);
        assertEq(stakeVault.getStake(agent3), STAKE);

        // Initial reputation scores
        assertEq(reputationManager.getScore(agent1), reputationManager.INITIAL_SCORE());
        assertEq(reputationManager.getScore(agent2), reputationManager.INITIAL_SCORE());
        assertEq(reputationManager.getScore(agent3), reputationManager.INITIAL_SCORE());

        // Step 5: Create a query
        bytes32 questionHash = keccak256("Explain Monad's parallel execution model");
        string[] memory queryCaps = new string[](1);
        queryCaps[0] = "nlp";
        uint256 deadline = block.timestamp + 30 minutes;

        vm.prank(requester);
        uint256 queryId = escrow.createQuery{value: BOUNTY}(queryCaps, questionHash, deadline);
        assertEq(queryId, 1);

        // Verify query state
        QueryEscrow.Query memory q = escrow.getQuery(queryId);
        assertEq(q.bounty, BOUNTY);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Open));

        // Step 6: Orchestrator moves status to Collecting
        vm.prank(deployer);
        escrow.updateStatus(queryId, QueryEscrow.QueryStatus.Collecting);

        // Step 7: Agent1 and Agent2 submit responses (agent3 has "vision" not "nlp" but can still respond)
        bytes32 resp1Hash = keccak256("Agent1 comprehensive explanation of Monad parallel execution");
        bytes32 resp2Hash = keccak256("Agent2 technical deep-dive into Monad architecture");

        vm.prank(agent1);
        escrow.submitResponse(queryId, resp1Hash);

        vm.prank(agent2);
        escrow.submitResponse(queryId, resp2Hash);

        // Verify 2 responses stored
        QueryEscrow.Response[] memory resps = escrow.getResponses(queryId);
        assertEq(resps.length, 2);
        assertEq(resps[0].agent, agent1);
        assertEq(resps[1].agent, agent2);

        // Step 8: Orchestrator selects agent1 as winner
        uint256 agent1BalanceBefore = agent1.balance;
        uint256 agent2BalanceBefore = agent2.balance;
        bytes32 memoryHash = keccak256("final_answer_memory_hash");

        vm.prank(deployer);
        escrow.updateStatus(queryId, QueryEscrow.QueryStatus.Scoring);

        vm.prank(deployer);
        escrow.selectWinner(queryId, agent1, memoryHash);

        // Step 9: Verify balances changed correctly
        uint256 agent1BalanceAfter = agent1.balance;
        uint256 agent2BalanceAfter = agent2.balance;

        assertEq(agent1BalanceAfter - agent1BalanceBefore, BOUNTY, "Winner should receive full bounty");
        assertEq(agent2BalanceAfter, agent2BalanceBefore, "Loser balance should not change");

        // Step 10: Verify query resolved
        QueryEscrow.Query memory resolvedQuery = escrow.getQuery(queryId);
        assertEq(uint256(resolvedQuery.status), uint256(QueryEscrow.QueryStatus.Resolved));
        assertEq(resolvedQuery.winner, agent1);
        assertEq(resolvedQuery.bounty, 0);

        // Step 11: Verify reputation updated
        uint256 agent1Score = reputationManager.getScore(agent1);
        uint256 agent2Score = reputationManager.getScore(agent2);

        assertEq(
            agent1Score,
            reputationManager.INITIAL_SCORE() + reputationManager.WIN_BONUS(),
            "Winner should have higher score"
        );
        assertEq(
            agent2Score,
            reputationManager.INITIAL_SCORE() - reputationManager.LOSS_PENALTY(),
            "Loser should have lower score"
        );

        // Agent3 did not participate, score unchanged
        assertEq(reputationManager.getScore(agent3), reputationManager.INITIAL_SCORE());

        // Step 12: Verify memory anchored in DecisionLedger
        assertTrue(ledger.verifyMemory(queryId, memoryHash), "Memory should be anchored");
        assertEq(ledger.totalAnchors(), 1);

        DecisionLedger.Anchor memory latestAnchor = ledger.getLatestAnchor(queryId);
        assertEq(latestAnchor.queryId, queryId);
        assertEq(latestAnchor.memoryHash, memoryHash);
        assertEq(latestAnchor.winner, agent1);
        assertEq(latestAnchor.round, 1);
    }

    function test_EndToEnd_QueryExpiry_RequesterRefunded() public {
        // Create query with 1 hour deadline
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(requester);
        uint256 queryId = escrow.createQuery{value: BOUNTY}(caps, keccak256("q"), block.timestamp + 1 hours);

        uint256 requesterBalanceBefore = requester.balance;

        // Warp past deadline
        vm.warp(block.timestamp + 2 hours);

        // Expire the query (anyone can call)
        escrow.expireQuery(queryId);

        uint256 requesterBalanceAfter = requester.balance;
        assertEq(requesterBalanceAfter - requesterBalanceBefore, BOUNTY, "Requester should get full refund");

        QueryEscrow.Query memory q = escrow.getQuery(queryId);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Failed));
    }

    function test_EndToEnd_AgentDeactivation_WithdrawalFlow() public {
        // Agent1 deactivates
        vm.prank(agent1);
        registry.deactivate();

        assertFalse(registry.isActive(agent1));

        // Withdrawal is pending
        (, , bool pending) = stakeVault.stakes(agent1);
        assertTrue(pending);

        // Cannot complete withdrawal yet (7 day cooldown)
        vm.expectRevert("StakeVault: cooldown active");
        stakeVault.completeWithdrawal(agent1);

        // Warp 7 days
        vm.warp(block.timestamp + 7 days + 1);

        uint256 balanceBefore = agent1.balance;
        stakeVault.completeWithdrawal(agent1);
        uint256 balanceAfter = agent1.balance;

        assertEq(balanceAfter - balanceBefore, STAKE);
        assertEq(stakeVault.getStake(agent1), 0);
    }

    function test_EndToEnd_MultipleQueries() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        // Create 3 queries
        vm.startPrank(requester);
        uint256 q1 = escrow.createQuery{value: 0.5 ether}(caps, keccak256("q1"), block.timestamp + 1 hours);
        uint256 q2 = escrow.createQuery{value: 0.3 ether}(caps, keccak256("q2"), block.timestamp + 2 hours);
        uint256 q3 = escrow.createQuery{value: 0.2 ether}(caps, keccak256("q3"), block.timestamp + 3 hours);
        vm.stopPrank();

        assertEq(escrow.queryCount(), 3);

        // Resolve q1 with agent1 winning
        vm.prank(agent1);
        escrow.submitResponse(q1, keccak256("a1"));

        vm.prank(deployer);
        escrow.selectWinner(q1, agent1, keccak256("mem1"));

        // Expire q2
        vm.warp(block.timestamp + 3 hours);
        escrow.expireQuery(q2);

        // Expire q3
        escrow.expireQuery(q3);

        // Verify final states
        assertEq(uint256(escrow.getQuery(q1).status), uint256(QueryEscrow.QueryStatus.Resolved));
        assertEq(uint256(escrow.getQuery(q2).status), uint256(QueryEscrow.QueryStatus.Failed));
        assertEq(uint256(escrow.getQuery(q3).status), uint256(QueryEscrow.QueryStatus.Failed));
    }

    function test_EndToEnd_EscalationFlow() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(requester);
        uint256 qId = escrow.createQuery{value: BOUNTY}(caps, keccak256("hard question"), block.timestamp + 10 minutes);

        // Agents respond in round 1
        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Round 1 response from agent1"));
        vm.prank(agent2);
        escrow.submitResponse(qId, keccak256("Round 1 response from agent2"));

        // Orchestrator transitions through Collecting → Scoring → Escalating
        vm.prank(deployer);
        escrow.updateStatus(qId, QueryEscrow.QueryStatus.Collecting);

        vm.prank(deployer);
        escrow.updateStatus(qId, QueryEscrow.QueryStatus.Scoring);

        vm.prank(deployer);
        escrow.escalate(qId);

        // Verify round 2 started
        QueryEscrow.Query memory q = escrow.getQuery(qId);
        assertEq(q.round, 2);
        assertEq(uint256(q.status), uint256(QueryEscrow.QueryStatus.Escalating));

        // Agents can respond again in round 2
        vm.prank(agent1);
        escrow.submitResponse(qId, keccak256("Improved round 2 answer"));
        vm.prank(agent2);
        escrow.submitResponse(qId, keccak256("Better round 2 answer from agent2"));

        // Now select winner from round 2
        uint256 winnerBalBefore = agent2.balance;

        vm.prank(deployer);
        escrow.selectWinner(qId, agent2, keccak256("final_memory"));

        uint256 winnerBalAfter = agent2.balance;
        assertEq(winnerBalAfter - winnerBalBefore, BOUNTY, "Agent2 should receive bounty after escalation");

        // Verify anchor
        DecisionLedger.Anchor memory anchor = ledger.getLatestAnchor(qId);
        assertEq(anchor.round, 2);
        assertEq(anchor.winner, agent2);
    }

    function test_EndToEnd_CapabilityLookup() public {
        // Agents with nlp capability
        address[] memory nlpAgents = registry.getAgentsByCapability("nlp");
        assertEq(nlpAgents.length, 2); // agent1 and agent2

        address[] memory reasoningAgents = registry.getAgentsByCapability("reasoning");
        assertEq(reasoningAgents.length, 1);
        assertEq(reasoningAgents[0], agent1);

        address[] memory visionAgents = registry.getAgentsByCapability("vision");
        assertEq(visionAgents.length, 1);
        assertEq(visionAgents[0], agent3);

        address[] memory codeAgents = registry.getAgentsByCapability("code");
        assertEq(codeAgents.length, 1);
        assertEq(codeAgents[0], agent2);
    }

    function test_EndToEnd_ReputationProgression() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        // Run 3 queries where agent1 wins all
        for (uint256 i = 0; i < 3; i++) {
            vm.prank(requester);
            uint256 qId = escrow.createQuery{value: 0.1 ether}(
                caps,
                keccak256(abi.encode("query", i)),
                block.timestamp + 1 hours
            );

            vm.prank(agent1);
            escrow.submitResponse(qId, keccak256(abi.encode("response", i)));
            vm.prank(agent2);
            escrow.submitResponse(qId, keccak256(abi.encode("response2", i)));

            vm.prank(deployer);
            escrow.selectWinner(qId, agent1, keccak256(abi.encode("mem", i)));
        }

        uint256 agent1Score = reputationManager.getScore(agent1);
        uint256 agent2Score = reputationManager.getScore(agent2);

        // Agent1 should have INITIAL + 3 * WIN_BONUS
        assertEq(
            agent1Score,
            reputationManager.INITIAL_SCORE() + 3 * reputationManager.WIN_BONUS()
        );
        // Agent2 should have INITIAL - 3 * LOSS_PENALTY
        assertEq(
            agent2Score,
            reputationManager.INITIAL_SCORE() - 3 * reputationManager.LOSS_PENALTY()
        );

        // Verify wins/losses in stats
        ReputationManager.AgentScore memory stats1 = reputationManager.getAgentStats(agent1);
        assertEq(stats1.wins, 3);
        assertEq(stats1.losses, 0);

        ReputationManager.AgentScore memory stats2 = reputationManager.getAgentStats(agent2);
        assertEq(stats2.wins, 0);
        assertEq(stats2.losses, 3);
    }
}
