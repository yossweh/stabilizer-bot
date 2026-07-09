# Stabilizer Finance Swap Bot

Automated swap bot for [Stabilizer Finance](https://app.stabilizer.finance/swap) on Sepolia testnet. Rotates through stablecoins (USDC → USDT → USDS → PYUSD → USDC) to earn SP points, with daily 20k SP cap tracking.

## Features

- 🔄 **Auto-rotation** — cycles through USDC/USDT/USDS/PYUSD
- 📊 **SP cap tracking** — 20k SP/day per wallet, auto-trims swaps
- ⏱️ **Cooldown** — 15s between swaps (protocol-enforced)
- 🔌 **Multi-RPC** — auto-failover between 3 Sepolia RPCs
- 🐧 **Cron-ready** — works with `screen` + cron for daily unattended runs

## Requirements

- Python 3.8+
- `web3`, `eth-account`

```bash
pip install web3 eth-account
```

## Setup

### 1. Clone & install

```bash
git clone https://github.com/yossweh/stabilizer-bot.git
cd stabilizer-bot
pip install -r requirements.txt
```

### 2. Add your wallet

Create `wallets.json` in the project directory:

```json
[
  {
    "address": "0xYourWalletAddress",
    "private_key": "0xYourPrivateKey"
  }
]
```

> ⚠️ `wallets.json` is in `.gitignore` — your private key stays local and is never pushed to GitHub.

### 3. Make sure your wallet is whitelisted

```bash
python stabilizer_bot.py --whitelist-check --wallet 0xYourWalletAddress
```

The wallet must be whitelisted on Stabilizer Finance to transact. Check at:
https://app.stabilizer.finance/api/whitelist/check/0xYourWalletAddress

### 4. Check balances

```bash
python stabilizer_bot.py --balances --wallet 0xYourWalletAddress
```

## Usage

### Whitelist check

```bash
python stabilizer_bot.py --whitelist-check --wallet 0x...
```

### Single swap

```bash
python stabilizer_bot.py --swap USDT USDS --wallet 0x...
```

### Full rotation (1 cycle)

```bash
python stabilizer_bot.py --rotate --wallet 0x... --cycles 1
```

### Run until daily cap (20k SP)

```bash
python stabilizer_bot.py --cron --wallet 0x... --cycles 100
```

### Faucet claim (testnet tokens)

```bash
python stabilizer_bot.py --faucet --wallet 0x...
```

### Show balances

```bash
python stabilizer_bot.py --balances --wallet 0x...
```

## Wallet Format

Create a `wallets.json` file in the project directory (it's in `.gitignore`, so it won't be pushed):

```json
[
  {
    "address": "0xYourWalletAddress",
    "private_key": "0xYourPrivateKey"
  }
]
```

> ⚠️ The `private_key` value above is a placeholder. Replace it with your actual private key. The file is ignored by git and will never be pushed.

### Alternative: Default Hermes path

The bot also supports `~/.agent/credentials/evm_wallets.json` (Hermes agent format) as a fallback.

## Cron Setup

```bash
# Daily at 08:00 WIB
0 8 * * * cd /path/to/stabilizer-bot && python stabilizer_bot.py --cron --wallet 0x... --cycles 100
```

Or use the provided `screen` wrapper:

```bash
bash ~/.hermes/scripts/stabilizer-daily-rotate.sh
```

## Contract Addresses (Sepolia)

| Token | Address |
|-------|---------|
| USDT | `0xee0418Bd560613fbcF924C36235AB1ec301D4933` |
| USDC | `0x77ef087024F87976aAdA0Aa7F73BB8EAe6E9dda1` |
| USDS | `0xF85938e2Bfc178026f60c5Ea50cC347D42C73b3D` |
| PYUSD | `0xF11Cf5a42c0a4F7e5BADe92c634Fd2649F4Ef53e` |
| Router | `0xFa6419a3d3503a016dF3A59F690734862CA2A78D` |
| AMM | `0xA3E36262f6899e27bB4B1802e8298e843E74CBC7` |
| Faucet | `0xd7ecBc8Bf36BAD24B7a921dc399C7a6cCEcD132f` |

## How It Works

1. **SP Points**: 1 SP = $100 swap volume
2. **Daily Cap**: 20,000 SP per wallet per UTC day
3. **Rotation**: USDC → USDT → USDS → PYUSD → USDC (uses max balance)
4. **Cooldown**: 15 seconds between swaps
5. **Gas**: Auto-calculated, 30% buffer, 800k limit

The bot tracks SP in `~/.hermes/cron/output/sp_tracker.json` and auto-resets daily.

## License

MIT