// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

contract ReputationManager is Ownable {
    address public escrowContract;

    struct AgentScore {
        uint256 score;        // 0-10000 (100 = 1.00)
        uint256 wins;
        uint256 losses;
        uint256 timeouts;
        uint256 lastActive;   // block number
    }

    mapping(address => AgentScore) public scores;

    uint256 public constant INITIAL_SCORE = 5000;
    uint256 public constant WIN_BONUS = 200;
    uint256 public constant LOSS_PENALTY = 50;
    uint256 public constant TIMEOUT_PENALTY = 150;
    uint256 public constant MAX_SCORE = 10000;

    event ScoreUpdated(address indexed agent, uint256 oldScore, uint256 newScore, string reason);
    event AgentInitialized(address indexed agent, uint256 initialScore);

    modifier onlyEscrow() {
        require(msg.sender == escrowContract, "ReputationManager: only escrow");
        _;
    }

    constructor() Ownable(msg.sender) {}

    function setEscrowContract(address _escrow) external onlyOwner {
        escrowContract = _escrow;
    }

    function initializeAgent(address agent) external onlyEscrow {
        if (scores[agent].score == 0) {
            scores[agent] = AgentScore({
                score: INITIAL_SCORE,
                wins: 0,
                losses: 0,
                timeouts: 0,
                lastActive: block.number
            });
            emit AgentInitialized(agent, INITIAL_SCORE);
        }
    }

    function recordWin(address agent) external onlyEscrow {
        AgentScore storage s = scores[agent];
        if (s.score == 0) s.score = INITIAL_SCORE;
        uint256 old = s.score;
        s.score = _min(s.score + WIN_BONUS, MAX_SCORE);
        s.wins++;
        s.lastActive = block.number;
        emit ScoreUpdated(agent, old, s.score, "win");
    }

    function recordLoss(address agent) external onlyEscrow {
        AgentScore storage s = scores[agent];
        if (s.score == 0) s.score = INITIAL_SCORE;
        uint256 old = s.score;
        s.score = s.score > LOSS_PENALTY ? s.score - LOSS_PENALTY : 1;
        s.losses++;
        s.lastActive = block.number;
        emit ScoreUpdated(agent, old, s.score, "loss");
    }

    function recordTimeout(address agent) external onlyEscrow {
        AgentScore storage s = scores[agent];
        if (s.score == 0) s.score = INITIAL_SCORE;
        uint256 old = s.score;
        s.score = s.score > TIMEOUT_PENALTY ? s.score - TIMEOUT_PENALTY : 1;
        s.timeouts++;
        emit ScoreUpdated(agent, old, s.score, "timeout");
    }

    function getScore(address agent) external view returns (uint256) {
        uint256 base = scores[agent].score;
        return base == 0 ? INITIAL_SCORE : base;
    }

    function getAgentStats(address agent) external view returns (AgentScore memory) {
        return scores[agent];
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
