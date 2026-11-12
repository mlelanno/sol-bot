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

# Import de la classe PaperTradingEngine
class PaperTradingEngine:
    TRADES_FILE = "/home/kilpi/trading_bot/logs/paper_trades.json"
    ACTIVE_POSITIONS_FILE = "/home/kilpi/trading_bot/data/active_positions.json"
    def __init__(self, initial_sol=1.0, trade_size_sol=0.05, slippage=0.15):
        self.sol_balance = initial_sol
        self.trade_size = trade_size_sol
        self.slippage = slippage
        os.makedirs(os.path.dirname(self.TRADES_FILE), exist_ok=True)
        os.makedirs(os.path.dirname(self.ACTIVE_POSITIONS_FILE), exist_ok=True)
        if not os.path.exists(self.TRADES_FILE):
            with open(self.TRADES_FILE, "w") as f:
                json.dump([], f)
        if not os.path.exists(self.ACTIVE_POSITIONS_FILE):
            with open(self.ACTIVE_POSITIONS_FILE, "w") as f:
                json.dump({}, f)
    def _load_positions(self):
        try:
            with open(self.ACTIVE_POSITIONS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    def _save_positions(self, positions):
        """Sauvegarde avec persistance - sauve toujours même si l'écriture directe échoue"""
        try:
            with open(self.ACTIVE_POSITIONS_FILE, "w") as f:
                json.dump(positions, f)
            log.info(f"Saved {len(positions)} positions successfully")
        except Exception as e:
            persist_path = "/home/kilpi/trading_bot/.persist_state.json"
            try:
                state = {"positions": positions, "timestamp": time.time()}
                with open(persist_path, "w") as f:
                    json.dump(state, f)
                log.warning(f"Direct save failed ({e}), persisted to {persist_path}")
            except Exception as e2:
                log.error(f"All saves failed! Primary error: {e}, Persist error: {e2}")
        return True
    def execute_buy(self, contract_address: str, ticker: str, price_usd: float, mc_usd: float, vol_usd: float):
        if self.sol_balance < self.trade_size:
            return False, "Solde SOL insuffisant"
        effective_price = price_usd * (1 + self.slippage)
        self.sol_balance -= self.trade_size
        trade_record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",
            "action": "BUY",
            "ticker": ticker,
            "contract": contract_address,
            "entry_price_usd": price_usd,
            "executed_price_usd": effective_price,
            "amount_sol": self.trade_size,
            "market_cap": mc_usd,
            "volume_24h": vol_usd,
            "remaining_sol": round(self.sol_balance, 4)
        }
        with open(self.TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(self.TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)
        tokens_held = self.trade_size / price_usd if price_usd > 0 else 0.0
        sol_invested = self.trade_size
        position_data = {
            "mint": contract_address,
            "ticker": ticker,
            "entry_price_usd": price_usd,
            "tokens_held": round(tokens_held, 6),
            "sol_invested": sol_invested,
            "entry_timestamp": time.time(),
            "tp1_executed": False
        }
        positions = self._load_positions()
        positions[contract_address] = position_data
        self._save_positions(positions)
        return True, trade_record
    def execute_sell(self, contract_address, ratio_to_sell, current_price_usd, reason):
        positions = self._load_positions()
        if contract_address not in positions:
            return False, f"Position introuvable pour {contract_address}", None
        position = positions[contract_address]
        entry_price = position["entry_price_usd"]
        tokens_held = position["tokens_held"]
        tokens_to_sell = tokens_held * ratio_to_sell
        sol_recovered = tokens_to_sell * current_price_usd
        self.sol_balance += sol_recovered
        pnl_sol = sol_recovered - (tokens_to_sell * entry_price)
        pnl_percentage = ((current_price_usd / entry_price) - 1) * 100 if entry_price > 0 else 0.0
        trade_record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",
            "action": "SELL",
            "ticker": position["ticker"],
            "contract": contract_address,
            "reason": reason,
            "entry_price_usd": entry_price,
            "exit_price_usd": current_price_usd,
            "tokens_sold": round(tokens_to_sell, 6),
            "sol_recovered": round(sol_recovered, 6),
            "pnl_sol": round(pnl_sol, 6),
            "pnl_percent": round(pnl_percentage, 2),
            "remaining_tokens": round(tokens_held - tokens_to_sell, 6)
        }
        with open(self.TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(self.TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)
        if ratio_to_sell == 1.0 or tokens_held - tokens_to_sell <= 0:
            del positions[contract_address]
        else:
            position["tokens_held"] = round(tokens_held - tokens_to_sell, 6)
            position["tp1_executed"] = True
        self._save_positions(positions)
        return True, f"Succès : {round(sol_recovered, 6)} SOL récupérés", None
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
    "So11111111111111111111111111111111111111112",  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
WALLET_MAP = {}
if os.path.exists(WALLETS_FILE):
    with open(WALLETS_FILE, "r", encoding="utf-8") as f:
        for w in json.load(f):
            addr = w.get("address", "").strip()
            if addr:
                WALLET_MAP[addr] = {
                    "name": w.get("name", "Unknown"),
                    "emoji": w.get("emoji", "🎯"),
                }
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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with session.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                console.print(f"[yellow]⚠️ Telegram HTTP {resp.status}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Erreur Telegram : {e}[/yellow]")

async def get_market_data(session: aiohttp.ClientSession, mint: str, sol_spent: float, tokens_received: float):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                data = await resp.json()
                pairs = data.get("pairs") or []
                if pairs:
                    pair = pairs[0]
                    price_usd = float(pair.get("priceUsd") or 0)
                    if price_usd > 0:
                        return {
                            "ticker": pair.get("baseToken", {}).get("symbol", "UNKNOWN"),
                            "price_usd": price_usd,
                            "mc_usd": float(pair.get("fdv") or 0),
                            "vol_usd": float(pair.get("volume", {}).get("h24") or 0),
                        }
    except Exception:
        pass
    fallback_price = ((sol_spent * 150.0) / tokens_received) if tokens_received > 0 else 0.000015
    return {
        "ticker": f"PUMP_{mint[:4]}",
        "price_usd": fallback_price,
        "mc_usd": fallback_price * 1_000_000_000,
        "vol_usd": sol_spent * 150.0,
    }

async def process_event(session: aiohttp.ClientSession, event: dict):
    fee_payer = event.get("feePayer", "")
    if not fee_payer or fee_payer not in WALLET_MAP:
        return
    swap = event.get("events", {}).get("swap", {})
    if not swap:
        return
    sol_spent = 0.0
    native_input = swap.get("nativeInput") or {}
    if native_input.get("amount"):
        sol_spent = float(native_input["amount"]) / 1e9
    else:
        for inp in swap.get("tokenInputs") or []:
            if inp.get("mint") == "So11111111111111111111111111111111111111112":
                raw = inp.get("rawTokenAmount") or {}
                amt = float(raw.get("tokenAmount", 0))
                dec = int(raw.get("decimals", 9))
                sol_spent = amt / (10 ** dec)
                break
    if sol_spent < MIN_SOL_BUY:
        return
    bought_mint = None
    tokens_received = 0.0
    for out in swap.get("tokenOutputs") or []:
        m = out.get("mint", "")
        if m and m not in IGNORED_MINTS:
            bought_mint = m
            raw = out.get("rawTokenAmount") or {}
            amt = float(raw.get("tokenAmount", 0))
            dec = int(raw.get("decimals", 6))
            tokens_received = amt / (10 ** dec) if amt > 0 else 0.0
            break
    if not bought_mint:
        return
    
    now = time.time()
    # Vérification stricte : feePayer doit EXISTER dans WALLET_MAP pour être comptabilisé
    if not fee_payer or fee_payer not in WALLET_MAP:
        return
    info = WALLET_MAP[fee_payer]
    clusters[bought_mint][fee_payer] = {"time": now, "sol": sol_spent, "tokens": tokens_received}
    cleanup_clusters(bought_mint, now)
    count = len(clusters[bought_mint])
    console.print(
        f"👀 [bold cyan]{info['name']} {info['emoji']}[/bold cyan] a acheté "
        f"[yellow]{sol_spent:.2f} SOL[/yellow] sur [green]{bought_mint[:6]}...{bought_mint[-4:]}[/green] "
        f"({count}/{REQUIRED_KOLS})"
    )
    if count >= REQUIRED_KOLS and bought_mint not in tokens_bought:
        tokens_bought.add(bought_mint)
        active_kols = clusters[bought_mint]
        total_sol = sum(d["sol"] for d in active_kols.values())
        kol_names = [f"{wallet_name(w, round(d['sol'], 2))}" for w, d in active_kols.items()]
        mkt = await get_market_data(session, bought_mint, sol_spent, tokens_received)
        console.print(Panel(
            f"[bold green]🚨 CONSENSUS KOL DÉTECTÉ ![/bold green]\n"
            f"Ticker : [bold]{mkt['ticker']}[/bold] | Mint : [yellow]{bought_mint}[/yellow]\n"
            f"KOLs   : {', '.join(kol_names)}\n"
            f"Prix   : ${mkt['price_usd']:.8f} | Total : {total_sol:.2f} SOL",
            title="🎯 SMART MONEY ENGINE", border_style="bright_green"
        ))
        paper_engine = PaperTradingEngine()
        success, _ = paper_engine.execute_buy(
            contract_address=bought_mint,
            ticker=mkt["ticker"],
            price_usd=mkt["price_usd"],
            mc_usd=mkt["mc_usd"],
            vol_usd=mkt["vol_usd"],
        )
        tg_msg = (
            f"🚨 <b>CONSENSUS KOL ({count} WALLETS)</b>\n\n"
            f"🪙 <b>Token :</b> ${mkt['ticker']}\n"
            f"📋 <code>{bought_mint}</code>\n"
            f"👥 <b>KOLs :</b> {', '.join(kol_names)}\n"
            f"💵 <b>Prix d'entrée :</b> ${mkt['price_usd']:.8f}\n"
            f"📊 <b>MC :</b> ${mkt['mc_usd']:,.0f}"
        )
        await send_telegram(session, tg_msg)

async def handle_webhook(request: web.Request):
    try:
        raw_data = await request.json()
        events = raw_data if isinstance(raw_data, list) else [raw_data]
        session = request.app["http_session"]
        for ev in events:
            if isinstance(ev, dict):
                try:
                    await process_event(session, ev)
                except Exception as e:
                    console.print(f"[red]Erreur event : {e}[/red]")
    except Exception as e:
        console.print(f"[red]Erreur payload : {e}[/red]")
    return web.Response(text="OK", status=200)

async def on_startup(app: web.Application):
    app["http_session"] = aiohttp.ClientSession()

async def on_cleanup(app: web.Application):
    await app["http_session"].close()

app = web.Application()
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
app.router.add_post("/webhook", handle_webhook)

if __name__ == "__main__":
    console.print(f"[bold green]🚀 Helius Listener actif sur 0.0.0.0:5000 ({len(WALLET_MAP)} wallets)[/bold green]")
    web.run_app(app, host="0.0.0.0", port=5000)
