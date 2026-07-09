#!/usr/bin/env python3
"""
Stabilizer Finance Swap Bot — rotation + SP cap tracking
"""
import argparse, json, os, time, sys, datetime, urllib.request
from decimal import Decimal
from eth_account import Account
from web3 import Web3

# ── CONFIG ──────────────────────────────────────────────────────
CHAIN_ID = 11155111
RPC_URLS = [
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://rpc.sepolia.org",
    "https://sepolia.drpc.org",
]

CONTRACTS = {
    "USDT":  "0xee0418Bd560613fbcF924C36235AB1ec301D4933",
    "USDC":  "0x77ef087024F87976aAdA0Aa7F73BB8EAe6E9dda1",
    "USDS":  "0xF85938e2Bfc178026f60c5Ea50cC347D42C73b3D",
    "PYUSD": "0xF11Cf5a42c0a4F7e5BADe92c634Fd2649F4Ef53e",
    "Router": "0xFa6419a3d3503a016dF3A59F690734862CA2A78D",
    "AMM":   "0xA3E36262f6899e27bB4B1802e8298e843E74CBC7",
    "Faucet":"0xd7ecBc8Bf36BAD24B7a921dc399C7a6cCEcD132f",
}

# Rotation order: start with USDC (has balance), go through all 4
ROTATION = ["USDC", "USDT", "USDS", "PYUSD", "USDC"]

DAILY_SP_CAP = 20000
COOLDOWN = 15
SP_TRACKER = os.path.expanduser("~/.hermes/cron/output/sp_tracker.json")
WALLET_FILE = os.path.expanduser("~/.agent/credentials/evm_wallets.json")

ERC20_ABI = [
    {"inputs":[{"name":"a","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"s","type":"address"},{"name":"a","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"o","type":"address"},{"name":"s","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
]

ROUTER_ABI = [
    {"inputs":[{"name":"t","type":"address"},{"name":"o","type":"address"},{"name":"a","type":"uint256"}],"name":"getAmountOut","outputs":[{"name":"","type":"uint256"},{"name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"t","type":"address"},{"name":"o","type":"address"},{"name":"a","type":"uint256"},{"name":"m","type":"uint256"}],"name":"swap","outputs":[{"name":"","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},
]

FAUCET_ABI = [
    {"inputs":[],"name":"faucet","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"u","type":"address"}],"name":"canClaimFaucet","outputs":[{"name":"","type":"bool"}],"stateMutability":"view","type":"function"},
]

# ── HELPERS ─────────────────────────────────────────────────────
def get_w3():
    for url in RPC_URLS:
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
            if w3.is_connected(): return w3
        except: pass
    raise ConnectionError("No RPC available")

def load_wallet(address=None):
    """Load wallet from wallets.json (local) or ~/.agent/credentials/evm_wallets.json"""
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallets.json")
    
    # Try local wallets.json first (user-friendly for other devs)
    if os.path.exists(local_path):
        with open(local_path) as f:
            wallets = json.load(f)
        if isinstance(wallets, list):
            if address:
                w = next(x for x in wallets if x["address"].lower() == address.lower())
            else:
                w = wallets[0]
        else:
            w = wallets[0] if isinstance(wallets, dict) and "wallets" in wallets else wallets
        acct = Account.from_key(w["private_key"])
        if address:
            assert acct.address.lower() == address.lower(), "Key mismatch"
        return acct
    
    # Fall back to default agent path
    with open(WALLET_FILE) as f:
        data = json.load(f)
    if address:
        w = next(x for x in data["wallets"] if x["address"].lower() == address.lower())
    else:
        w = data["wallets"][data["main_wallet_index"]]
    acct = Account.from_key(w["private_key"])
    assert acct.address.lower() == w["address"].lower(), "Key mismatch"
    return acct

def gp(w3, mult=1.3):
    return int(w3.eth.gas_price * mult)

def wait_receipt(tx_hash, timeout=120):
    deadline = time.time() + timeout
    # Use sepolia.drpc.org as primary for receipt checking (most reliable)
    primary_rpc = "https://sepolia.drpc.org"
    backup_rpcs = ["https://ethereum-sepolia-rpc.publicnode.com", "https://rpc.ankr.com/eth_sepolia"]
    
    while time.time() < deadline:
        for url in [primary_rpc] + backup_rpcs:
            try:
                w3t = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
                r = w3t.eth.get_transaction_receipt(tx_hash)
                if r and r.get("status") is not None:
                    return r
            except: pass
        time.sleep(3)
    
    # Last resort: check if tx is still pending
    try:
        w3t = Web3(Web3.HTTPProvider(primary_rpc, request_kwargs={"timeout": 5}))
        tx = w3t.eth.get_transaction(tx_hash)
        if tx and tx.get("blockNumber") is None:
            print(f"  ⏳ tx still pending: {tx_hash[:16]}...", flush=True)
            # Wait more
            time.sleep(30)
            for url in [primary_rpc] + backup_rpcs:
                try:
                    w3t = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
                    r = w3t.eth.get_transaction_receipt(tx_hash)
                    if r: return r
                except: pass
    except: pass
    
    return None

def token_balance(w3, token, addr):
    c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_ABI)
    bal = c.functions.balanceOf(addr).call()
    dec = c.functions.decimals().call()
    return bal, dec

def ensure_approve(w3, acct, token, spender, amount):
    spender = Web3.to_checksum_address(spender)
    token = Web3.to_checksum_address(token)
    c = w3.eth.contract(address=token, abi=ERC20_ABI)
    if c.functions.allowance(acct.address, spender).call() >= amount:
        return None
    tx = c.functions.approve(spender, amount).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 100000, "gasPrice": gp(w3), "chainId": CHAIN_ID,
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    wait_receipt(h)
    return h

def today_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

def load_sp():
    if not os.path.exists(SP_TRACKER): return {}
    with open(SP_TRACKER) as f:
        data = json.load(f)
    today = today_utc()
    return {k: v for k, v in data.items() if v.get("date") == today}

def record_sp(wallet, volume_usd):
    wallet = wallet.lower()
    data = load_sp()
    current = data.get(wallet, {"date": today_utc(), "sp": 0.0})["sp"]
    sp_earned = volume_usd / 100.0
    data[wallet] = {"date": today_utc(), "sp": current + sp_earned}
    os.makedirs(os.path.dirname(SP_TRACKER), exist_ok=True)
    with open(SP_TRACKER, "w") as f:
        json.dump(data, f, indent=2)
    return data[wallet]["sp"]

def check_whitelist(address):
    url = f"https://app.stabilizer.finance/api/whitelist/check/{address}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return bool(json.loads(r.read()).get("whitelisted"))
    except: return False

# ── SWAP ────────────────────────────────────────────────────────
def execute_swap(w3, acct, token_in, token_out, amount_wei, slippage_bps=50):
    router = w3.eth.contract(address=Web3.to_checksum_address(CONTRACTS["Router"]), abi=ROUTER_ABI)
    token_in_cs = Web3.to_checksum_address(token_in)
    token_out_cs = Web3.to_checksum_address(token_out)
    
    amount_out, is_multi = router.functions.getAmountOut(token_in_cs, token_out_cs, amount_wei).call()
    if amount_out == 0:
        print("zero_out", flush=True)
        return None, 0
    
    min_out = int(amount_out * (10000 - slippage_bps) // 10000)
    ensure_approve(w3, acct, token_in_cs, CONTRACTS["Router"], amount_wei)
    
    tx = router.functions.swap(token_in_cs, token_out_cs, amount_wei, min_out).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 800000, "gasPrice": gp(w3), "chainId": CHAIN_ID,
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = wait_receipt(h)
    return receipt, amount_out

# ── CLI ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--whitelist-check", action="store_true")
    parser.add_argument("--balances", action="store_true")
    parser.add_argument("--faucet", action="store_true")
    parser.add_argument("--swap", nargs=2, metavar=("FROM", "TO"))
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--cron", action="store_true")
    parser.add_argument("--wallet", help="Wallet address (required)")
    parser.add_argument("--cycles", type=int, default=100)
    args = parser.parse_args()
    
    if not args.wallet:
        parser.print_help()
        print("\n❌ --wallet is required. Use --wallet 0xYourAddress")
        sys.exit(1)
    
    acct = load_wallet(args.wallet)
    w3 = get_w3()
    
    if args.whitelist_check:
        wl = check_whitelist(acct.address)
        print(f"Wallet: {acct.address}")
        print(f"Whitelisted: {wl}")
        sys.exit(0)
    
    if args.balances:
        print(f"Wallet: {acct.address}")
        print(f"ETH: {w3.eth.get_balance(acct.address) / 1e18:.4f}")
        for name, addr in CONTRACTS.items():
            if name in ("Router", "AMM", "Faucet"):
                continue
            c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ERC20_ABI)
            bal = c.functions.balanceOf(acct.address).call()
            dec = c.functions.decimals().call()
            print(f"{name}: {bal / 10**dec:.2f}")
        sys.exit(0)
    
    if args.faucet:
        faucet = w3.eth.contract(address=Web3.to_checksum_address(CONTRACTS["Faucet"]), abi=FAUCET_ABI)
        if faucet.functions.canClaimFaucet(acct.address).call():
            tx = faucet.functions.faucet().build_transaction({
                "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
                "gas": 200000, "gasPrice": gp(w3), "chainId": CHAIN_ID,
            })
            signed = acct.sign_transaction(tx)
            h = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
            r = wait_receipt(h)
            print(f"Faucet claimed: {h}")
        else:
            print("Faucet not available (cooldown)")
        sys.exit(0)
    
    if args.swap:
        token_in = CONTRACTS[args.swap[0].upper()]
        token_out = CONTRACTS[args.swap[1].upper()]
        bal, dec = token_balance(w3, token_in, acct.address)
        if bal == 0:
            print(f"No {args.swap[0]} balance")
            sys.exit(1)
        print(f"Swapping {bal / 10**dec:.2f} {args.swap[0]}")
        receipt, out = execute_swap(w3, acct, token_in, token_out, bal)
        if receipt:
            vol = bal / 10**dec
            sp = record_sp(acct.address, vol)
            tx_hash = receipt["transactionHash"].hex()
            print(f"✅ {args.swap[0]}→{args.swap[1]}: {vol:.2f} USD | SP: {sp:.2f} | tx: {tx_hash[:16]}...")
        sys.exit(0)
    
    if args.rotate or args.cron:
        today = today_utc()
        print(f"🌐 Stabilizer Rotation — {today}")
        print(f"Wallet: {acct.address[:6]}...{acct.address[-4:]}")
        print(f"ETH: {w3.eth.get_balance(acct.address) / 1e18:.4f}")
        
        sp_tracker = load_sp()
        current_sp = sp_tracker.get(acct.address.lower(), {}).get("sp", 0.0)
        print(f"SP today: {current_sp:.2f}/{DAILY_SP_CAP}")
        
        if current_sp >= DAILY_SP_CAP:
            print("✅ Daily SP cap reached. Exiting.")
            sys.exit(0)
        
        hops = 0
        total_sp = current_sp
        
        for cycle in range(1, args.cycles + 1):
            if total_sp >= DAILY_SP_CAP:
                print(f"⛔ Cap reached at cycle {cycle}")
                break
            
            print(f"\n🔄 Cycle {cycle}")
            
            for i in range(len(ROTATION) - 1):
                if total_sp >= DAILY_SP_CAP:
                    break
                
                from_token = ROTATION[i]
                to_token = ROTATION[i + 1]
                token_in = CONTRACTS[from_token]
                token_out = CONTRACTS[to_token]
                
                bal, dec = token_balance(w3, token_in, acct.address)
                if bal == 0:
                    print(f"  ⚠️ No {from_token} balance")
                    continue
                
                vol_usd = bal / 10**dec
                sp_this = vol_usd / 100.0
                
                if total_sp + sp_this > DAILY_SP_CAP:
                    remaining_sp = DAILY_SP_CAP - total_sp
                    max_vol = remaining_sp * 100.0
                    ratio = max_vol / vol_usd
                    if ratio < 0.01:
                        print(f"  ⛔ Remaining cap too small ({remaining_sp:.2f} SP)")
                        break
                    bal = int(bal * ratio)
                    vol_usd = bal / 10**dec
                
                print(f"  {from_token}→{to_token}: {vol_usd:.2f} USD...", end=" ", flush=True)
                receipt, out = execute_swap(w3, acct, token_in, token_out, bal)
                
                if receipt and receipt["status"] == 1:
                    total_sp = record_sp(acct.address, vol_usd)
                    hops += 1
                    tx_hash = receipt["transactionHash"].hex()
                    print(f"✅ SP: {total_sp:.2f} | {tx_hash[:10]}...")
                    time.sleep(COOLDOWN)
                else:
                    print("❌ Failed")
                    time.sleep(5)
            
            if total_sp >= DAILY_SP_CAP:
                break
        
        print(f"\n{'='*40}")
        print(f"✅ Done: {hops} hops, {total_sp:.2f}/{DAILY_SP_CAP} SP")
        sys.exit(0)
    
    parser.print_help()