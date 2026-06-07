// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/AgentRegistry.sol";
import "../src/StakeVault.sol";
import "../src/ReputationManager.sol";

contract AgentRegistryTest is Test {
    StakeVault public stakeVault;
    ReputationManager public reputationManager;
    AgentRegistry public registry;

    address public deployer = address(0xDEAD);
    address public agent1 = address(0x1111);
    address public agent2 = address(0x2222);

    uint256 public constant MIN_STAKE = 0.01 ether;

    function setUp() public {
        vm.startPrank(deployer);

        stakeVault = new StakeVault();
        reputationManager = new ReputationManager();
        registry = new AgentRegistry(address(stakeVault), address(reputationManager));

        // Wire up contracts
        stakeVault.setRegistryContract(address(registry));
        // reputationManager escrow will be set to a mock escrow (registry calls it via escrow)
        // For registry to call reputationManager.initializeAgent, reputationManager must allow registry
        // We set escrowContract to registry for these tests
        reputationManager.setEscrowContract(address(registry));

        vm.stopPrank();

        vm.deal(agent1, 10 ether);
        vm.deal(agent2, 10 ether);
    }

    // ---- Registration Tests ----

    function test_RegisterAgent() public {
        string[] memory caps = new string[](2);
        caps[0] = "nlp";
        caps[1] = "vision";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        AgentRegistry.Agent memory a = registry.getAgent(agent1);
        assertEq(a.wallet, agent1);
        assertTrue(a.active);
        assertEq(a.capabilities.length, 2);
        assertEq(a.capabilities[0], "nlp");
        assertEq(a.capabilities[1], "vision");
        assertEq(a.metadataURI, "ipfs://meta1");
    }

    function test_RegisterAgent_StakeDeposited() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        assertEq(stakeVault.getStake(agent1), MIN_STAKE);
    }

    function test_RegisterAgent_ReputationInitialized() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        uint256 score = reputationManager.getScore(agent1);
        assertEq(score, reputationManager.INITIAL_SCORE());
    }

    function test_RegisterAgent_CapabilityIndexed() public {
        string[] memory caps = new string[](2);
        caps[0] = "nlp";
        caps[1] = "vision";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        address[] memory nlpAgents = registry.getAgentsByCapability("nlp");
        assertEq(nlpAgents.length, 1);
        assertEq(nlpAgents[0], agent1);

        address[] memory visionAgents = registry.getAgentsByCapability("vision");
        assertEq(visionAgents.length, 1);
        assertEq(visionAgents[0], agent1);
    }

    function test_RegisterAgent_InsufficientStake() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        vm.expectRevert("AgentRegistry: insufficient stake");
        registry.register{value: 0.001 ether}(caps, "ipfs://meta1");
    }

    function test_RegisterAgent_NoCapabilities() public {
        string[] memory caps = new string[](0);

        vm.prank(agent1);
        vm.expectRevert("AgentRegistry: need capabilities");
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");
    }

    function test_RegisterAgent_AlreadyRegistered() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.startPrank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        vm.expectRevert("AgentRegistry: already registered");
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");
        vm.stopPrank();
    }

    // ---- Active Agent List Tests ----

    function test_GetActiveAgents() public {
        string[] memory caps1 = new string[](1);
        caps1[0] = "nlp";
        string[] memory caps2 = new string[](1);
        caps2[0] = "vision";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps1, "ipfs://meta1");
        vm.prank(agent2);
        registry.register{value: MIN_STAKE}(caps2, "ipfs://meta2");

        address[] memory active = registry.getActiveAgents();
        assertEq(active.length, 2);
    }

    function test_GetActiveAgents_ExcludesDeactivated() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");
        vm.prank(agent2);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta2");

        vm.prank(agent1);
        registry.deactivate();

        address[] memory active = registry.getActiveAgents();
        assertEq(active.length, 1);
        assertEq(active[0], agent2);
    }

    // ---- Capability Update Tests ----

    function test_UpdateCapabilities() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        string[] memory newCaps = new string[](2);
        newCaps[0] = "vision";
        newCaps[1] = "audio";

        vm.prank(agent1);
        registry.updateCapabilities(newCaps);

        string[] memory stored = registry.getAgentCapabilities(agent1);
        assertEq(stored.length, 2);
        assertEq(stored[0], "vision");
        assertEq(stored[1], "audio");

        // Old capability should be removed from index
        address[] memory nlpAgents = registry.getAgentsByCapability("nlp");
        assertEq(nlpAgents.length, 0);

        // New capability should be in index
        address[] memory visionAgents = registry.getAgentsByCapability("vision");
        assertEq(visionAgents.length, 1);
    }

    function test_UpdateCapabilities_NotRegistered() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        vm.expectRevert("AgentRegistry: not registered");
        registry.updateCapabilities(caps);
    }

    // ---- Deactivation Tests ----

    function test_Deactivate() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        vm.prank(agent1);
        registry.deactivate();

        assertFalse(registry.isActive(agent1));
    }

    function test_Deactivate_InitiatesWithdrawal() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        vm.prank(agent1);
        registry.deactivate();

        (uint256 amount, uint256 initiatedAt, bool pending) = stakeVault.stakes(agent1);
        assertTrue(pending);
        assertGt(initiatedAt, 0);
    }

    function test_Deactivate_NotActive() public {
        vm.prank(agent1);
        vm.expectRevert("AgentRegistry: not active");
        registry.deactivate();
    }

    // ---- isActive Tests ----

    function test_IsActive_True() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");

        assertTrue(registry.isActive(agent1));
    }

    function test_IsActive_False_Unregistered() public {
        assertFalse(registry.isActive(agent1));
    }

    // ---- Capability filter respects active status ----

    function test_GetAgentsByCapability_OnlyActive() public {
        string[] memory caps = new string[](1);
        caps[0] = "nlp";

        vm.prank(agent1);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta1");
        vm.prank(agent2);
        registry.register{value: MIN_STAKE}(caps, "ipfs://meta2");

        vm.prank(agent1);
        registry.deactivate();

        address[] memory nlpAgents = registry.getAgentsByCapability("nlp");
        assertEq(nlpAgents.length, 1);
        assertEq(nlpAgents[0], agent2);
    }
}
