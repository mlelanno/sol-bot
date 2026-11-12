import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import json
import time
from collections import defaultdict
import aiohttp
from aiohttp import web
from rich.console import Console
from rich.panel import Panel
from core.paper_engine import paper_engine

console = Console()
BASE_DIR = "/home/kilpi/trading_bot"
ENV_FILE = os.path.join(BASE_DIR, ".env")
WALLETS_FILE = os.path.join(BASE_DIR, "data/smart_wallets.json")

if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

IGNORED_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}

WALLET_MAP = {}
if os.path.exists(WALLETS_FILE):
    with open(WALLETS_FILE, "r", encoding="utf-8") as f:
        for w in json.load(f):
            addr = w.get("address", "").strip()
            if addr:
                WALLET_MAP[addr] = {"name": w.get("name", "Unknown"), "emoji": w.get("emoji", "🎯")}

clusters = defaultdict(dict)
tokens_bought = set()
CONSENSUS_WINDOW = 60
REQUIRED_KOLS = 2
MIN_SOL_BUY = 0.05

def cleanup_clusters(mint: str, now: float):
    expired = [w for w, d in clusters[mint].items() if now - d["time"] > CONSENSUS_WINDOW]
    for w in expired:
        del clusters[mint][w]

async def send_telegram(session: aiohttp.ClientSession, message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5) as resp:
            pass
    except Exception: pass

async def get_market_data(session: aiohttp.ClientSession, mint: str, sol_spent: float, tokens_received: float):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    try:
        async with session.get(url, timeout=4) as resp:
            if resp.status == 200:
                data = await resp.json()
                pairs = data.get("pairs") or []
                if pairs:
                    pair = pairs[0]
                    price_usd = float(pair.get("priceUsd") or 0)
                    if price_usd > 0:
                        return {"ticker": pair.get("baseToken", {}).get("symbol", "UNKNOWN"), "price_usd": price_usd, "mc_usd": float(pair.get("fdv") or 0), "vol_usd": float(pair.get("volume", {}).get("h24") or 0)}
    except Exception: pass
    fallback_price = ((sol_spent * 150.0) / tokens_received) if tokens_received > 0 else 0.000015
    return {"ticker": f"PUMP_{mint[:4]}", "price_usd": fallback_price, "mc_usd": fallback_price * 1_000_000_000, "vol_usd": sol_spent * 150.0}

async def process_event(session: aiohttp.ClientSession, event: dict):
    # 1. Identifier le KOL partout (Padre / Banana Gun incluent le KOL dans transfers, pas feePayer)
    candidates = [event.get("feePayer")]
    for t in event.get("tokenTransfers") or []:
        candidates.extend([t.get("fromUserAccount"), t.get("toUserAccount")])
    for n in event.get("nativeTransfers") or []:
        candidates.extend([n.get("fromUserAccount"), n.get("toUserAccount")])
    for a in event.get("accountData") or []:
        candidates.append(a.get("account"))

    kol_wallet = next((c for c in candidates if c and c in WALLET_MAP), None)
    if not kol_wallet: return
    info = WALLET_MAP[kol_wallet]

    # 2. Extraire les flux
    swap = event.get("events", {}).get("swap", {})
    sol_spent, tokens_received, bought_mint = 0.0, 0.0, None

    if swap:
        if swap.get("nativeInput") and swap["nativeInput"].get("amount"):
            sol_spent = float(swap["nativeInput"]["amount"]) / 1e9
        else:
            for inp in swap.get("tokenInputs") or []:
                if inp.get("mint") == "So11111111111111111111111111111111111111112":
                    sol_spent = float(inp.get("rawTokenAmount", {}).get("tokenAmount", 0)) / (10 ** int(inp.get("rawTokenAmount", {}).get("decimals", 9)))
                    break
        for out in swap.get("tokenOutputs") or []:
            m = out.get("mint", "")
            if m and m not in IGNORED_MINTS:
                bought_mint = m
                tokens_received = float(out.get("rawTokenAmount", {}).get("tokenAmount", 0)) / (10 ** int(out.get("rawTokenAmount", {}).get("decimals", 6)))
                break

    # Fallback pour Padre / PumpSwap / Banana Gun
    if not bought_mint or sol_spent <= 0:
        for t in event.get("tokenTransfers") or []:
            if t.get("toUserAccount") == kol_wallet and t.get("mint") not in IGNORED_MINTS:
                bought_mint = t.get("mint")
                tokens_received += float(t.get("tokenAmount") or 0)
            if t.get("fromUserAccount") == kol_wallet and t.get("mint") == "So11111111111111111111111111111111111111112":
                sol_spent += float(t.get("tokenAmount") or 0)
        
        if sol_spent <= 0:
            for n in event.get("nativeTransfers") or []:
                if n.get("fromUserAccount") == kol_wallet:
                    sol_spent += float(n.get("amount") or 0) / 1e9

    if not bought_mint or sol_spent < MIN_SOL_BUY: return

    # 3. Enregistrer et alerter
    now = time.time()
    clusters[bought_mint][kol_wallet] = {"time": now, "sol": sol_spent, "tokens": tokens_received}
    cleanup_clusters(bought_mint, now)
    count = len(clusters[bought_mint])
    console.print(f"👀 [bold cyan]{info['name']} {info['emoji']}[/bold cyan] a acheté [yellow]{sol_spent:.2f} SOL[/yellow] sur [green]{bought_mint[:6]}...{bought_mint[-4:]}[/green] ({count}/{REQUIRED_KOLS})")

    if count >= REQUIRED_KOLS and bought_mint not in tokens_bought:
        tokens_bought.add(bought_mint)
        active_kols = clusters[bought_mint]
        total_sol = sum(d["sol"] for d in active_kols.values())
        kol_names = [f"{WALLET_MAP[w]['name']} ({d['sol']:.2f} SOL)" for w, d in active_kols.items()]
        mkt = await get_market_data(session, bought_mint, sol_spent, tokens_received)
        console.print(Panel(f"[bold green]🚨 CONSENSUS KOL DÉTECTÉ ![/bold green]\nTicker : [bold]{mkt['ticker']}[/bold] | Mint : [yellow]{bought_mint}[/yellow]\nKOLs   : {', '.join(kol_names)}\nPrix   : ${mkt['price_usd']:.8f} | Total : {total_sol:.2f} SOL", title="🎯 SMART MONEY ENGINE", border_style="bright_green"))
        paper_engine.execute_buy(contract_address=bought_mint, ticker=mkt["ticker"], price_usd=mkt["price_usd"], mc_usd=mkt["mc_usd"], vol_usd=mkt["vol_usd"])
        await send_telegram(session, f"🚨 <b>CONSENSUS KOL ({count} WALLETS)</b>\n\n🪙 <b>Token :</b> ${mkt['ticker']}\n📋 <code>{bought_mint}</code>\n👥 <b>KOLs :</b> {', '.join(kol_names)}\n💵 <b>Prix d'entrée :</b> ${mkt['price_usd']:.8f}\n📊 <b>MC :</b> ${mkt['mc_usd']:,.0f}")

async def handle_webhook(request: web.Request):
    try:
        raw_bytes = await request.read()
        if not raw_bytes: return web.Response(text="OK", status=200)
        events = json.loads(raw_bytes.decode("utf-8"))
        events = events if isinstance(events, list) else [events]
        session = request.app["http_session"]
        for ev in events:
            if isinstance(ev, dict):
                await process_event(session, ev)
    except (asyncio.CancelledError, ConnectionResetError): pass
    except Exception as e: console.print(f"[red]Erreur event : {e}[/red]")
    return web.Response(text="OK", status=200)

async def on_startup(app: web.Application): app["http_session"] = aiohttp.ClientSession()
async def on_cleanup(app: web.Application): await app["http_session"].close()

app = web.Application()
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
app.router.add_post("/webhook", handle_webhook)

if __name__ == "__main__":
    console.print(f"[bold green]🚀 Helius Listener actif sur 0.0.0.0:5000 ({len(WALLET_MAP)} wallets)[/bold green]")
    web.run_app(app, host="0.0.0.0", port=5000)
