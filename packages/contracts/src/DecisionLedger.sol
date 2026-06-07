// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

contract DecisionLedger is Ownable {
    address public escrowContract;

    struct Anchor {
        uint256 queryId;
        bytes32 memoryHash;
        uint8 round;
        uint256 blockNumber;
        uint256 timestamp;
        address winner;
    }

    mapping(uint256 => Anchor[]) public anchors;
    uint256 public totalAnchors;

    event MemoryAnchored(
        uint256 indexed queryId,
        bytes32 memoryHash,
        uint8 round,
        address winner,
        uint256 blockNumber
    );

    modifier onlyEscrow() {
        require(msg.sender == escrowContract, "DecisionLedger: only escrow");
        _;
    }

    constructor() Ownable(msg.sender) {}

    function setEscrowContract(address _escrow) external onlyOwner {
        escrowContract = _escrow;
    }

    function anchor(
        uint256 queryId,
        bytes32 memoryHash,
        uint8 round,
        address winner
    ) external onlyEscrow {
        anchors[queryId].push(Anchor({
            queryId: queryId,
            memoryHash: memoryHash,
            round: round,
            blockNumber: block.number,
            timestamp: block.timestamp,
            winner: winner
        }));
        totalAnchors++;
        emit MemoryAnchored(queryId, memoryHash, round, winner, block.number);
    }

    function getAnchors(uint256 queryId) external view returns (Anchor[] memory) {
        return anchors[queryId];
    }

    function getLatestAnchor(uint256 queryId) external view returns (Anchor memory) {
        Anchor[] storage a = anchors[queryId];
        require(a.length > 0, "DecisionLedger: no anchors");
        return a[a.length - 1];
    }

    function verifyMemory(uint256 queryId, bytes32 hash) external view returns (bool) {
        Anchor[] storage a = anchors[queryId];
        for (uint256 i = 0; i < a.length; i++) {
            if (a[i].memoryHash == hash) return true;
        }
        return false;
    }
}
