import os, sys, json, time, asyncio, aiohttp
from collections import defaultdict
from aiohttp import web
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

from core.scoring_engine import ScoringEngine
from core.risk_scanner import RiskScanner
from core.paper_engine import PaperTradingEngine

IGNORED_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
}

SOL_PRICE = float(os.getenv("SOL_PRICE_USD", "185.0"))
CONFIG_FILE = os.path.join(BASE_DIR, "data", "bot_config.json")
REJECTS_FILE = os.path.join(BASE_DIR, "logs", "rejected_tokens.jsonl")
WALLETS_FILE = os.path.join(BASE_DIR, "data", "smart_wallets.json")

scoring_engine = ScoringEngine()
risk_scanner = RiskScanner()
paper_engine = PaperTradingEngine()
clusters = defaultdict(dict)
META_CACHE = {}

def load_wallet_map():
    wmap = {}
    if os.path.exists(WALLETS_FILE):
        try:
            data = json.load(open(WALLETS_FILE, encoding="utf-8"))
            items = data if isinstance(data, list) else (data.get("wallets") or data.get("kols") or data)
            if isinstance(items, dict):
                for k, v in items.items():
                    wmap[k] = v.get("name", k[:6]) if isinstance(v, dict) else str(v)
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        addr = item.get("address") or item.get("wallet") or item.get("pubkey")
                        if addr:
                            wmap[addr] = item.get("name") or item.get("twitter") or addr[:6]
                    elif isinstance(item, str):
                        wmap[item] = item[:6]
        except Exception as e:
            print(f"[WARN] Wallets load: {e}")
    return wmap

WALLET_MAP = load_wallet_map()

def load_live_config():
    cfg = {"bot_paused": False, "min_score": 60, "trade_size_sol": 0.1, "stop_loss_pct": -25.0, "take_profit_pct": 60.0}
    if os.path.exists(CONFIG_FILE):
        try: cfg.update(json.load(open(CONFIG_FILE, encoding="utf-8")))
        except Exception: pass
    return cfg

def log_rejection(mint, ticker, name, score, mc_usd, reason):
    b = "Micro" if mc_usd < 100_000 else ("Low" if mc_usd < 500_000 else "Mid")
    row = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mint": mint,
        "ticker": ticker,
        "name": name,
        "score": round(float(score or 0), 1),
        "mc_bracket": b,
        "reason": str(reason)
    }
    try:
        lines = open(REJECTS_FILE, encoding="utf-8").readlines()[-199:] if os.path.exists(REJECTS_FILE) else []
        lines.append(json.dumps(row) + "\n")
        open(REJECTS_FILE, "w", encoding="utf-8").writelines(lines)
    except Exception:
        pass

async def fetch_meta(session, mint):
    if mint in META_CACHE:
        return META_CACHE[mint]
    key = os.getenv("HELIUS_API_KEY", "")
    rpc = os.getenv("HELIUS_RPC_URL") or (f"https://mainnet.helius-rpc.com/?api-key={key}" if key else "")
    if rpc:
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint}}
            async with session.post(rpc, json=payload, timeout=aiohttp.ClientTimeout(total=2.5)) as r:
                if r.status == 200:
                    d = await r.json()
                    m = (((d.get("result") or {}).get("content") or {}).get("metadata") or {})
                    sym = (m.get("symbol") or "").strip().replace("\x00", "")
                    nm = (m.get("name") or "").strip().replace("\x00", "")
                    if sym:
                        META_CACHE[mint] = (sym, nm)
                        return META_CACHE[mint]
        except Exception:
            pass
    return (f"PUMP_{mint[:4]}", "")

async def process_event(session, event):
    cands = [event.get("feePayer")] + [
        x for t in (event.get("tokenTransfers") or []) for x in (t.get("fromUserAccount"), t.get("toUserAccount"))
    ] + [
        x for n in (event.get("nativeTransfers") or []) for x in (n.get("fromUserAccount"), n.get("toUserAccount"))
    ]
    kol = next((c for c in cands if c and c in WALLET_MAP), None)
    if not kol:
        return

    ss = 0.0
    received_by_mint = defaultdict(float)
    sold = False

    for t in event.get("tokenTransfers") or []:
        tm = t.get("mint")
        amt = float(t.get("tokenAmount") or 0.0)
        if not tm or amt <= 0:
            continue
        if t.get("fromUserAccount") == kol:
            if tm == "So11111111111111111111111111111111111111112":
                ss += amt
            elif tm not in IGNORED_MINTS:
                sold = True
        elif t.get("toUserAccount") == kol and tm not in IGNORED_MINTS:
            received_by_mint[tm] += amt

    if ss == 0.0:
        sent_lamports = sum(float(n.get("amount") or 0) for n in (event.get("nativeTransfers") or []) if n.get("fromUserAccount") == kol)
        recv_lamports = sum(float(n.get("amount") or 0) for n in (event.get("nativeTransfers") or []) if n.get("toUserAccount") == kol)
        ss = max(0.0, (sent_lamports - recv_lamports) / 1e9)

    if sold or not received_by_mint or ss < 0.05:
        return

    mint, tr = max(received_by_mint.items(), key=lambda kv: kv[1])
    if tr <= 0:
        return

    now = time.time()
    clusters[mint][kol] = {"time": now, "sol": round(ss, 4), "name": WALLET_MAP[kol]}
    clusters[mint] = {k: v for k, v in clusters[mint].items() if now - v["time"] <= 90}

    cfg = load_live_config()
    if cfg.get("bot_paused"):
        return

    p_usd = (ss / tr) * SOL_PRICE
    mc = p_usd * 1_000_000_000
    if p_usd <= 0 or mc > 50_000_000:
        return

    tk, mn = await fetch_meta(session, mint)
    ml = scoring_engine._load_ml_data()

    # Parallélisation stricte : Scoring (avec Fast-Track IA) + RiskScanner (Top 10 & Anti-Bundling)
    score_task = scoring_engine.calculate_score(mint=mint, kols_involved=clusters[mint], mc_usd=mc, ml_data=ml, ticker=tk, mint_name=mn)
    risk_task = risk_scanner.evaluate_token(mint, mc_usd=mc)
    score, (ok_r, rsn) = await asyncio.gather(score_task, risk_task)

    ms = float(cfg.get("min_score", 60))
    if score < ms:
        log_rejection(mint, tk, mn, score, mc, f"Score {score:.0f}/{ms:.0f}")
        return

    if not ok_r:
        reason_str = ", ".join(rsn) if isinstance(rsn, list) else str(rsn)
        log_rejection(mint, tk, mn, score, mc, reason_str)
        return

    base_sz = float(cfg.get("trade_size_sol", 0.1))
    sz = scoring_engine.get_dynamic_sizing(score, base_sz)

    ok_b, rec = await paper_engine.execute_buy(
        contract_address=mint, ticker=tk, price_usd=p_usd, mc_usd=mc,
        vol_usd=ss * SOL_PRICE, trade_size=sz, kols=list(clusters[mint].keys()), score=score
    )
    if ok_b:
        print(f"🔥 [BUY V2] {tk} ({mint[:6]}) | Score: {score} | Size: {sz} SOL | MC: ${mc:,.0f}")

async def handle_webhook(request):
    try:
        data = await request.json()
        events = data if isinstance(data, list) else [data]
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
            for ev in events:
                if isinstance(ev, dict):
                    await process_event(session, ev)
    except Exception as e:
        print(f"[WEBHOOK WARN] {e}")
    return web.Response(text="OK", status=200)

if __name__ == "__main__":
    print(f"🚀 Helius Listener V2 actif sur port 5000 ({len(WALLET_MAP)} KOLs suivis)...")
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_post("/", handle_webhook)
    web.run_app(app, host="0.0.0.0", port=5000, print=None)
