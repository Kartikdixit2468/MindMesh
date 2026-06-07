// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract StakeVault is Ownable, ReentrancyGuard {
    address public registryContract;

    struct StakeInfo {
        uint256 amount;
        uint256 withdrawInitiatedAt;
        bool withdrawPending;
    }

    mapping(address => StakeInfo) public stakes;
    uint256 public constant WITHDRAWAL_COOLDOWN = 7 days;
    uint256 public constant MIN_STAKE = 0.01 ether;

    event Deposited(address indexed agent, uint256 amount, uint256 total);
    event WithdrawalInitiated(address indexed agent, uint256 amount);
    event WithdrawalCompleted(address indexed agent, uint256 amount);
    event Slashed(address indexed agent, uint256 amount, string reason);

    modifier onlyRegistry() {
        require(msg.sender == registryContract, "StakeVault: only registry");
        _;
    }

    constructor() Ownable(msg.sender) {}

    function setRegistryContract(address _registry) external onlyOwner {
        registryContract = _registry;
    }

    function deposit(address agent) external payable {
        require(msg.value >= MIN_STAKE, "StakeVault: below min stake");
        stakes[agent].amount += msg.value;
        stakes[agent].withdrawPending = false;
        emit Deposited(agent, msg.value, stakes[agent].amount);
    }

    function initiateWithdrawal(address agent) external onlyRegistry {
        StakeInfo storage s = stakes[agent];
        require(s.amount > 0, "StakeVault: no stake");
        require(!s.withdrawPending, "StakeVault: already pending");
        s.withdrawPending = true;
        s.withdrawInitiatedAt = block.timestamp;
        emit WithdrawalInitiated(agent, s.amount);
    }

    function completeWithdrawal(address agent) external nonReentrant {
        StakeInfo storage s = stakes[agent];
        require(s.withdrawPending, "StakeVault: no pending withdrawal");
        require(
            block.timestamp >= s.withdrawInitiatedAt + WITHDRAWAL_COOLDOWN,
            "StakeVault: cooldown active"
        );
        uint256 amount = s.amount;
        s.amount = 0;
        s.withdrawPending = false;
        payable(agent).transfer(amount);
        emit WithdrawalCompleted(agent, amount);
    }

    function slash(address agent, uint256 amount, string calldata reason) external onlyRegistry {
        StakeInfo storage s = stakes[agent];
        uint256 slashAmount = amount > s.amount ? s.amount : amount;
        s.amount -= slashAmount;
        payable(owner()).transfer(slashAmount);
        emit Slashed(agent, slashAmount, reason);
    }

    function getStake(address agent) external view returns (uint256) {
        return stakes[agent].amount;
    }
}
