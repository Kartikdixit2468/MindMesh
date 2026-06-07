"""
VectorStore — ChromaDB for RAG on proposal discussions.
Embeddings are stored locally in .chroma/ and can be rebuilt from chain events.
The Merkle root of all embeddings is anchored on-chain at settlement.
"""
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger("orchestrator.vector_store")


class VectorStore:
    """
    Wraps ChromaDB for semantic search over discussion messages.
    Falls back to keyword search if chromadb is not installed.
    """

    def __init__(self, persist_dir: str = ".chroma"):
        self._client = None
        self._collection = None
        self._persist_dir = persist_dir
        self._messages: list[dict] = []  # fallback if no chromadb
        self._try_init()

    def _try_init(self):
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection(
                name="discussions",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"[VectorStore] ChromaDB ready at {self._persist_dir}")
        except ImportError:
            logger.warning("[VectorStore] chromadb not installed — using in-memory keyword fallback")
        except Exception as e:
            logger.warning(f"[VectorStore] ChromaDB init failed: {e} — using fallback")

    def add_message(
        self,
        proposal_id: str,
        msg_id: str,
        content: str,
        agent_name: str = "",
        role_name: str = "",
        round_num: int = 1,
        round_type: str = "initial",
    ) -> None:
        """Add a discussion message for semantic indexing."""
        if self._collection is not None:
            try:
                self._collection.add(
                    ids=[msg_id],
                    documents=[content],
                    metadatas=[{
                        "proposal_id": proposal_id,
                        "agent_name": agent_name,
                        "role_name": role_name,
                        "round_num": str(round_num),
                        "round_type": round_type,
                    }],
                )
            except Exception as e:
                logger.debug(f"[VectorStore] add_message error: {e}")
        else:
            self._messages.append({
                "id": msg_id, "proposal_id": proposal_id,
                "content": content, "role_name": role_name,
                "round_num": round_num, "round_type": round_type,
            })

    def get_context(self, proposal_id: str, query: str, n: int = 6) -> str:
        """Return formatted context string for RAG synthesis."""
        results = self._search(proposal_id, query, n)
        if not results:
            return ""
        lines = ["## Relevant prior discussion points:\n"]
        for r in results:
            role = r.get("role_name", "Agent")
            content = r.get("content", "")
            round_num = r.get("round_num", "?")
            lines.append(f"**{role} (Round {round_num}):** {content}\n")
        return "\n".join(lines)

    def _search(self, proposal_id: str, query: str, n: int) -> list[dict]:
        if self._collection is not None:
            try:
                res = self._collection.query(
                    query_texts=[query],
                    n_results=min(n, self._collection.count()),
                    where={"proposal_id": proposal_id},
                )
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                return [{"content": d, **m} for d, m in zip(docs, metas)]
            except Exception:
                pass

        # Keyword fallback
        matches = [
            m for m in self._messages
            if m["proposal_id"] == proposal_id and
            any(w.lower() in m["content"].lower() for w in query.split()[:5])
        ]
        return matches[:n]

    def merkle_root(self, proposal_id: str) -> str:
        """Compute a Merkle root over all messages for a proposal (for on-chain anchoring)."""
        if self._collection is not None:
            try:
                res = self._collection.get(where={"proposal_id": proposal_id})
                docs = res.get("documents", [])
                if not docs:
                    return "0x" + "0" * 64
                leaves = [hashlib.sha256(d.encode()).digest() for d in docs]
                while len(leaves) > 1:
                    if len(leaves) % 2:
                        leaves.append(leaves[-1])
                    leaves = [
                        hashlib.sha256(leaves[i] + leaves[i + 1]).digest()
                        for i in range(0, len(leaves), 2)
                    ]
                return "0x" + leaves[0].hex()
            except Exception:
                pass

        # Fallback
        msgs = [m for m in self._messages if m["proposal_id"] == proposal_id]
        if not msgs:
            return "0x" + "0" * 64
        combined = hashlib.sha256("|".join(m["content"] for m in msgs).encode()).hexdigest()
        return "0x" + combined


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
