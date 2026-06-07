"""
Monad chain client — wraps web3.py for all on-chain interactions.
Uses the deployer wallet as the orchestrator signer.
"""
import json
import logging
from typing import Optional

from eth_account import Account
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.exceptions import ContractLogicError

from .config import settings

logger = logging.getLogger("orchestrator.chain")

# Minimal ABIs — only the functions we call
AGENT_REGISTRY_ABI = [
    {"inputs": [{"name": "capability", "type": "string"}], "name": "getAgentsByCapability", "outputs": [{"type": "address[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "wallet", "type": "address"}], "name": "getAgent", "outputs": [{"components": [{"name": "wallet", "type": "address"}, {"name": "capabilities", "type": "string[]"}, {"name": "metadataURI", "type": "string"}, {"name": "active", "type": "bool"}, {"name": "registeredAt", "type": "uint256"}], "type": "tuple"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "wallet", "type": "address"}], "name": "isActive", "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getActiveAgents", "outputs": [{"type": "address[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "capabilities", "type": "string[]"}, {"name": "metadataURI", "type": "string"}], "name": "register", "outputs": [], "stateMutability": "payable", "type": "function"},
]

QUERY_ESCROW_ABI = [
    {"inputs": [{"name": "capabilities", "type": "string[]"}, {"name": "questionHash", "type": "bytes32"}, {"name": "deadline", "type": "uint256"}], "name": "createQuery", "outputs": [{"type": "uint256"}], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}, {"name": "responseHash", "type": "bytes32"}], "name": "submitResponse", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}, {"name": "winner", "type": "address"}, {"name": "memoryHash", "type": "bytes32"}], "name": "selectWinner", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}], "name": "escalate", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}], "name": "expireQuery", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}, {"name": "newStatus", "type": "uint8"}], "name": "updateStatus", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "queryId", "type": "uint256"}], "name": "getQuery", "outputs": [{"components": [{"name": "id", "type": "uint256"}, {"name": "requester", "type": "address"}, {"name": "questionHash", "type": "bytes32"}, {"name": "capabilities", "type": "string[]"}, {"name": "bounty", "type": "uint256"}, {"name": "deadline", "type": "uint256"}, {"name": "status", "type": "uint8"}, {"name": "winner", "type": "address"}, {"name": "round", "type": "uint8"}, {"name": "createdAt", "type": "uint256"}], "type": "tuple"}], "stateMutability": "view", "type": "function"},
    # Events
    {"anonymous": False, "inputs": [{"indexed": True, "name": "queryId", "type": "uint256"}, {"indexed": True, "name": "requester", "type": "address"}, {"indexed": False, "name": "questionHash", "type": "bytes32"}, {"indexed": False, "name": "capabilities", "type": "string[]"}, {"indexed": False, "name": "bounty", "type": "uint256"}, {"indexed": False, "name": "deadline", "type": "uint256"}], "name": "QueryCreated", "type": "event"},
    {"anonymous": False, "inputs": [{"indexed": True, "name": "queryId", "type": "uint256"}, {"indexed": True, "name": "winner", "type": "address"}, {"indexed": False, "name": "bounty", "type": "uint256"}, {"indexed": False, "name": "memoryHash", "type": "bytes32"}, {"indexed": False, "name": "round", "type": "uint8"}], "name": "WinnerSelected", "type": "event"},
    {"anonymous": False, "inputs": [{"indexed": True, "name": "queryId", "type": "uint256"}, {"indexed": True, "name": "agent", "type": "address"}, {"indexed": False, "name": "responseHash", "type": "bytes32"}, {"indexed": False, "name": "round", "type": "uint8"}], "name": "ResponseSubmitted", "type": "event"},
]

REPUTATION_MANAGER_ABI = [
    {"inputs": [{"name": "agent", "type": "address"}], "name": "getScore", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "agent", "type": "address"}], "name": "getAgentStats", "outputs": [{"components": [{"name": "score", "type": "uint256"}, {"name": "wins", "type": "uint256"}, {"name": "losses", "type": "uint256"}, {"name": "timeouts", "type": "uint256"}, {"name": "lastActive", "type": "uint256"}], "type": "tuple"}], "stateMutability": "view", "type": "function"},
]


class ChainClient:
    def __init__(self):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.MONAD_RPC_URL))
        self.account = Account.from_key(settings.DEPLOYER_PRIVATE_KEY)
        self._nonce_lock = False
        self._nonce: Optional[int] = None

    def _registry(self):
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.AGENT_REGISTRY_ADDRESS),
            abi=AGENT_REGISTRY_ABI,
        )

    def _escrow(self):
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.QUERY_ESCROW_ADDRESS),
            abi=QUERY_ESCROW_ABI,
        )

    def _reputation(self):
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.REPUTATION_MANAGER_ADDRESS),
            abi=REPUTATION_MANAGER_ABI,
        )

    async def _get_nonce(self) -> int:
        return await self.w3.eth.get_transaction_count(self.account.address)

    async def _send_tx(self, fn, value: int = 0) -> str:
        """Build, sign and send a transaction. Returns tx hash."""
        if not settings.contracts_deployed:
            logger.warning("[CHAIN] Contracts not deployed — tx skipped (offline mode)")
            return "0x" + "0" * 64

        try:
            nonce = await self._get_nonce()
            gas_price = await self.w3.eth.gas_price
            tx = await fn.build_transaction(
                {
                    "from": self.account.address,
                    "nonce": nonce,
                    "value": value,
                    "gasPrice": int(gas_price * 1.1),
                }
            )
            tx["gas"] = await self.w3.eth.estimate_gas(tx)
            signed = self.account.sign_transaction(tx)
            tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            hash_hex = tx_hash.hex()
            logger.info(f"[CHAIN] Tx confirmed: {hash_hex} (block {receipt.blockNumber})")
            return hash_hex
        except ContractLogicError as e:
            logger.error(f"[CHAIN] Contract revert: {e}")
            raise
        except Exception as e:
            logger.error(f"[CHAIN] TX error: {e}", exc_info=True)
            raise

    async def get_reputation(self, address: str) -> int:
        if not settings.contracts_deployed:
            return 5000
        try:
            return await self._reputation().functions.getScore(
                self.w3.to_checksum_address(address)
            ).call()
        except Exception:
            return 5000

    async def get_agents_by_capability(self, capability: str) -> list[str]:
        if not settings.contracts_deployed:
            return []
        try:
            return await self._registry().functions.getAgentsByCapability(capability).call()
        except Exception as e:
            logger.warning(f"[CHAIN] get_agents_by_capability error: {e}")
            return []

    async def select_winner(
        self, chain_query_id: int, winner: str, memory_hash: str
    ) -> str:
        if not settings.contracts_deployed:
            logger.info("[CHAIN] Offline mode — winner selection simulated")
            return "0x" + "0" * 64

        memory_bytes = bytes.fromhex(
            memory_hash[2:] if memory_hash.startswith("0x") else memory_hash
        )
        # Pad to 32 bytes
        memory_bytes32 = memory_bytes[:32].ljust(32, b"\x00")

        fn = self._escrow().functions.selectWinner(
            chain_query_id,
            self.w3.to_checksum_address(winner),
            memory_bytes32,
        )
        return await self._send_tx(fn)

    async def escalate_query(self, chain_query_id: int) -> str:
        if not settings.contracts_deployed:
            return "0x" + "0" * 64
        # First update status to Scoring
        fn_scoring = self._escrow().functions.updateStatus(chain_query_id, 2)  # Scoring = 2
        await self._send_tx(fn_scoring)
        fn = self._escrow().functions.escalate(chain_query_id)
        return await self._send_tx(fn)

    async def expire_query(self, chain_query_id: int) -> str:
        if not settings.contracts_deployed:
            return "0x" + "0" * 64
        fn = self._escrow().functions.expireQuery(chain_query_id)
        return await self._send_tx(fn)

    async def register_agent(
        self,
        private_key: str,
        capabilities: list[str],
        metadata_uri: str,
        stake_wei: int,
    ) -> str:
        account = Account.from_key(private_key)
        nonce = await self.w3.eth.get_transaction_count(account.address)
        gas_price = await self.w3.eth.gas_price

        fn = self._registry().functions.register(capabilities, metadata_uri)
        tx = await fn.build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "value": stake_wei,
                "gasPrice": int(gas_price * 1.1),
            }
        )
        tx["gas"] = await self.w3.eth.estimate_gas(tx)
        signed = account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return tx_hash.hex()

    async def listen_for_events(self, callback) -> None:
        """Stream QueryCreated events and call callback(event_data)."""
        if not settings.contracts_deployed:
            logger.info("[CHAIN] Offline mode — event listener not started")
            return

        escrow = self._escrow()
        event_filter = await escrow.events.QueryCreated.create_filter(fromBlock="latest")
        logger.info("[CHAIN] Listening for QueryCreated events on Monad testnet...")

        while True:
            try:
                for event in await event_filter.get_new_entries():
                    await callback(
                        {
                            "chain_query_id": event["args"]["queryId"],
                            "requester": event["args"]["requester"],
                            "capabilities": event["args"]["capabilities"],
                            "bounty": str(event["args"]["bounty"]),
                            "deadline": event["args"]["deadline"],
                            "tx_hash": event["transactionHash"].hex(),
                            "block_number": event["blockNumber"],
                        }
                    )
            except Exception as e:
                logger.error(f"[CHAIN] Event listener error: {e}", exc_info=True)

            import asyncio
            await asyncio.sleep(3)
