# MonadBlitz — Hackathon project Makefile
# Usage: make <target>

.PHONY: help install install-contracts install-orchestrator install-agents install-cli \
        orchestrator agents cli web \
        contracts-build contracts-test deploy-testnet \
        docker-up docker-down \
        demo wallets clean

help:
	@echo ""
	@echo "  MonadBlitz — Decentralized AI Agent Coordination on Monad"
	@echo ""
	@echo "  Setup:"
	@echo "    make install          — install ALL Python packages (uv)"
	@echo "    make install-contracts — install Foundry deps"
	@echo ""
	@echo "  Run (local, requires Postgres + Redis running):"
	@echo "    make orchestrator     — start FastAPI orchestrator"
	@echo "    make agents           — start all 3 agent nodes"
	@echo "    make cli              — launch textual terminal dashboard"
	@echo "    make web              — start Next.js frontend"
	@echo ""
	@echo "  Contracts:"
	@echo "    make contracts-build  — forge build"
	@echo "    make contracts-test   — forge test -vv"
	@echo "    make deploy-testnet   — deploy to Monad testnet"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-up        — docker compose up (all services)"
	@echo "    make docker-down      — docker compose down"
	@echo ""
	@echo "  Utilities:"
	@echo "    make wallets          — generate 5 wallets → wallets.json"
	@echo "    make demo             — run end-to-end demo query"
	@echo "    make clean            — remove build artifacts"
	@echo ""

# ── Install ────────────────────────────────────────────────────────────────────

install: install-orchestrator install-agents install-cli

install-orchestrator:
	cd packages/orchestrator && uv pip install -e .

install-agents:
	cd packages/agents && uv pip install -e .

install-cli:
	cd packages/cli && uv pip install -e .

install-contracts:
	cd packages/contracts && forge install

# ── Run (local) ────────────────────────────────────────────────────────────────

orchestrator:
	cd packages/orchestrator && uvicorn orchestrator.main:app --reload --host 0.0.0.0 --port 8000

agents:
	cd packages/agents && python -m agents.launcher

cli:
	cd packages/cli && monadblitz-cli

web:
	cd packages/web && npm run dev

# ── Contracts ──────────────────────────────────────────────────────────────────

contracts-build:
	cd packages/contracts && forge build

contracts-test:
	cd packages/contracts && forge test -vv

deploy-testnet:
	cd packages/contracts && forge script script/Deploy.s.sol:Deploy \
		--rpc-url https://testnet-rpc.monad.xyz \
		--broadcast \
		--verify \
		--verifier-url https://testnet.monadexplorer.com/api \
		-vvvv

# ── Docker ─────────────────────────────────────────────────────────────────────

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Utilities ──────────────────────────────────────────────────────────────────

wallets:
	python scripts/generate_wallets.py

demo:
	python scripts/run_demo.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	cd packages/contracts && forge clean
