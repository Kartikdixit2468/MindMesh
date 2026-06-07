"""
Generate 5 Ethereum wallets for MonadBlitz deployment.

Usage:
    python scripts/generate_wallets.py

Outputs wallets.json with addresses and private keys.
NEVER commit wallets.json — it is in .gitignore.
"""
import json
import os
import sys

try:
    from eth_account import Account
except ImportError:
    sys.exit("eth-account not installed. Run: pip install eth-account")

Account.enable_unaudited_hdwallet_features()

ROLES = ["deployer", "alpha_agent", "beta_agent", "gamma_agent", "treasury"]

wallets = []
for role in ROLES:
    acct = Account.create()
    wallets.append(
        {
            "role": role,
            "address": acct.address,
            "private_key": acct.key.hex(),
        }
    )

out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wallets.json")
with open(out_path, "w") as f:
    json.dump(wallets, f, indent=2)

print(f"Generated {len(wallets)} wallets → {out_path}")
print()
print("Add to .env:")
print(f"  DEPLOYER_PRIVATE_KEY={wallets[0]['private_key']}")
print(f"  ALPHA_PRIVATE_KEY={wallets[1]['private_key']}")
print(f"  BETA_PRIVATE_KEY={wallets[2]['private_key']}")
print(f"  GAMMA_PRIVATE_KEY={wallets[3]['private_key']}")
print()
print("Fund these addresses on Monad testnet faucet:")
for w in wallets:
    print(f"  {w['role']:15} {w['address']}")
print()
print("NEVER commit wallets.json — it contains private keys!")
