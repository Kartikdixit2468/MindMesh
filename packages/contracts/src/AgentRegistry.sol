// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "./StakeVault.sol";
import "./ReputationManager.sol";

contract AgentRegistry is Ownable {
    StakeVault public stakeVault;
    ReputationManager public reputationManager;

    struct Agent {
        address wallet;
        string[] capabilities;
        string metadataURI;
        bool active;
        uint256 registeredAt;
    }

    mapping(address => Agent) public agents;
    address[] public agentList;
    mapping(string => address[]) public capabilityIndex;

    uint256 public constant MIN_STAKE = 0.01 ether;

    event AgentRegistered(address indexed agent, string[] capabilities, uint256 stake);
    event AgentUpdated(address indexed agent, string[] capabilities);
    event AgentDeactivated(address indexed agent);

    constructor(address _stakeVault, address _reputationManager) Ownable(msg.sender) {
        stakeVault = StakeVault(_stakeVault);
        reputationManager = ReputationManager(_reputationManager);
    }

    function register(
        string[] calldata capabilities,
        string calldata metadataURI
    ) external payable {
        require(msg.value >= MIN_STAKE, "AgentRegistry: insufficient stake");
        require(!agents[msg.sender].active, "AgentRegistry: already registered");
        require(capabilities.length > 0, "AgentRegistry: need capabilities");

        stakeVault.deposit{value: msg.value}(msg.sender);
        reputationManager.initializeAgent(msg.sender);

        agents[msg.sender] = Agent({
            wallet: msg.sender,
            capabilities: capabilities,
            metadataURI: metadataURI,
            active: true,
            registeredAt: block.timestamp
        });

        agentList.push(msg.sender);

        for (uint256 i = 0; i < capabilities.length; i++) {
            capabilityIndex[capabilities[i]].push(msg.sender);
        }

        emit AgentRegistered(msg.sender, capabilities, msg.value);
    }

    function updateCapabilities(string[] calldata capabilities) external {
        require(agents[msg.sender].active, "AgentRegistry: not registered");

        string[] storage old = agents[msg.sender].capabilities;
        for (uint256 i = 0; i < old.length; i++) {
            _removeFromCapabilityIndex(old[i], msg.sender);
        }

        agents[msg.sender].capabilities = capabilities;

        for (uint256 i = 0; i < capabilities.length; i++) {
            capabilityIndex[capabilities[i]].push(msg.sender);
        }

        emit AgentUpdated(msg.sender, capabilities);
    }

    function deactivate() external {
        require(agents[msg.sender].active, "AgentRegistry: not active");
        agents[msg.sender].active = false;
        stakeVault.initiateWithdrawal(msg.sender);
        emit AgentDeactivated(msg.sender);
    }

    function getAgent(address wallet) external view returns (Agent memory) {
        return agents[wallet];
    }

    function getActiveAgents() external view returns (address[] memory) {
        uint256 count = 0;
        for (uint256 i = 0; i < agentList.length; i++) {
            if (agents[agentList[i]].active) count++;
        }
        address[] memory result = new address[](count);
        uint256 j = 0;
        for (uint256 i = 0; i < agentList.length; i++) {
            if (agents[agentList[i]].active) result[j++] = agentList[i];
        }
        return result;
    }

    function getAgentsByCapability(string calldata capability) external view returns (address[] memory) {
        address[] storage all = capabilityIndex[capability];
        uint256 count = 0;
        for (uint256 i = 0; i < all.length; i++) {
            if (agents[all[i]].active) count++;
        }
        address[] memory result = new address[](count);
        uint256 j = 0;
        for (uint256 i = 0; i < all.length; i++) {
            if (agents[all[i]].active) result[j++] = all[i];
        }
        return result;
    }

    function getAgentCapabilities(address wallet) external view returns (string[] memory) {
        return agents[wallet].capabilities;
    }

    function isActive(address wallet) external view returns (bool) {
        return agents[wallet].active;
    }

    function _removeFromCapabilityIndex(string storage cap, address agent) internal {
        address[] storage list = capabilityIndex[cap];
        for (uint256 i = 0; i < list.length; i++) {
            if (list[i] == agent) {
                list[i] = list[list.length - 1];
                list.pop();
                break;
            }
        }
    }
}
