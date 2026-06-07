// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/StakeVault.sol";
import "../src/ReputationManager.sol";
import "../src/DecisionLedger.sol";
import "../src/AgentRegistry.sol";
import "../src/QueryEscrow.sol";

contract DeployScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy StakeVault
        StakeVault stakeVault = new StakeVault();
        console.log("StakeVault deployed at:", address(stakeVault));

        // 2. Deploy ReputationManager
        ReputationManager reputationManager = new ReputationManager();
        console.log("ReputationManager deployed at:", address(reputationManager));

        // 3. Deploy DecisionLedger
        DecisionLedger decisionLedger = new DecisionLedger();
        console.log("DecisionLedger deployed at:", address(decisionLedger));

        // 4. Deploy AgentRegistry (depends on StakeVault + ReputationManager)
        AgentRegistry agentRegistry = new AgentRegistry(
            address(stakeVault),
            address(reputationManager)
        );
        console.log("AgentRegistry deployed at:", address(agentRegistry));

        // 5. Deploy QueryEscrow (depends on AgentRegistry + ReputationManager + DecisionLedger)
        QueryEscrow queryEscrow = new QueryEscrow(
            address(agentRegistry),
            address(reputationManager),
            address(decisionLedger)
        );
        console.log("QueryEscrow deployed at:", address(queryEscrow));

        // 6. Wire up contracts
        reputationManager.setEscrowContract(address(queryEscrow));
        console.log("ReputationManager: escrowContract set to QueryEscrow");

        decisionLedger.setEscrowContract(address(queryEscrow));
        console.log("DecisionLedger: escrowContract set to QueryEscrow");

        stakeVault.setRegistryContract(address(agentRegistry));
        console.log("StakeVault: registryContract set to AgentRegistry");

        queryEscrow.setOrchestratorAddress(deployer);
        console.log("QueryEscrow: orchestratorAddress set to deployer:", deployer);

        vm.stopBroadcast();

        // Output deployment summary as JSON
        string memory json = string(abi.encodePacked(
            "{\n",
            '  "network": "monad_testnet",\n',
            '  "chainId": 10143,\n',
            '  "deployer": "', vm.toString(deployer), '",\n',
            '  "contracts": {\n',
            '    "StakeVault": "', vm.toString(address(stakeVault)), '",\n',
            '    "ReputationManager": "', vm.toString(address(reputationManager)), '",\n',
            '    "DecisionLedger": "', vm.toString(address(decisionLedger)), '",\n',
            '    "AgentRegistry": "', vm.toString(address(agentRegistry)), '",\n',
            '    "QueryEscrow": "', vm.toString(address(queryEscrow)), '"\n',
            '  }\n',
            "}"
        ));

        console.log("\n=== Deployment Summary ===");
        console.log(json);

        // Write to file
        vm.writeFile("deployments/monad_testnet.json", json);
        console.log("\nDeployment addresses saved to deployments/monad_testnet.json");
    }
}
