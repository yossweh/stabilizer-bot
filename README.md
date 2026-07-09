# Stabilizer Swap Bot

Automated stablecoin rotation bot for [Stabilizer Finance](https://app.stabilizer.finance/swap) testnet.

Rotates USDC → USDT → USDS → PYUSD → USDC to stack SP points. Stops at 20k SP/day.

## Quick Start

```bash
pip install web3 eth-account
```

Create `wallets.json`:

```json
[{"address": "0xYourAddress", "private_key": "0xYourPK"}]
```

Check if you're whitelisted:

```bash
python stabilizer_bot.py --whitelist-check --wallet 0xYourAddress
```

Run a full rotation:

```bash
python stabilizer_bot.py --rotate --wallet 0xYourAddress
```

## Commands

| Command | What it does |
|---------|-------------|
| `--whitelist-check` | Check if wallet is whitelisted |
| `--balances` | Show token balances |
| `--swap USDT USDS` | Single swap between two tokens |
| `--rotate` | Full rotation cycle (USDC→USDT→USDS→PYUSD→USDC) |
| `--cron` | Keep rotating until 20k SP cap |
| `--faucet` | Claim testnet tokens |
| `--cycles N` | Max cycles (default 100) |

## Tokens (Sepolia)

| Token | Address |
|-------|---------|
| USDT | `0xee0418Bd560613fbcF924C36235AB1ec301D4933` |
| USDC | `0x77ef087024F87976aAdA0Aa7F73BB8EAe6E9dda1` |
| USDS | `0xF85938e2Bfc178026f60c5Ea50cC347D42C73b3D` |
| PYUSD | `0xF11Cf5a42c0a4F7e5BADe92c634Fd2649F4Ef53e` |
| Router | `0xFa6419a3d3503a016dF3A59F690734862CA2A78D` |

## How it works

- 1 SP = $100 volume
- 20k SP cap per wallet per day
- Bot uses max balance, trims last swap if cap is close
- 15s cooldown between swaps
- Auto-switches RPC if one is slow

SP is tracked in `~/.hermes/cron/output/sp_tracker.json` and resets daily.

## License

MIT