import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import json
import time
from collections import defaultdict
import aiohttp
from rich.console import Console
from rich.panel import Panel

from core.paper_engine import paper_engine

console = Console()
WALLETS_FILE = "/home/kilpi/trading_bot/data/smart_wallets.json"

def load_smart_wallets():
    if not os.path.exists(WALLETS_FILE):
        console.print(f"[bold red]❌ Fichier introuvable : {WALLETS_FILE}[/bold red]")
        return {}, []
    with open(WALLETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    wallet_map = {}
    for w in data:
        addr = w.get("address", "").strip()
        if addr:
            wallet_map[addr] = {
                "name": w.get("name", "Unknown"),
                "emoji": w.get("emoji", "🎯")
            }
    return wallet_map, list(wallet_map.keys())

WALLET_MAP, TRACKED_KEYS = load_smart_wallets()

clusters = defaultdict(dict)
tokens_bought = set()
CONSENSUS_WINDOW = 60
REQUIRED_KOLS = 2

def cleanup_clusters(mint: str, now: float):
    expired = [w for w, d in clusters[mint].items() if now - d["time"] > CONSENSUS_WINDOW]
    for w in expired:
        del clusters[mint][w]

async def process_buy_event(data: dict):
    wallet_addr = data.get("traderPublicKey") or data.get("from") or ""
    mint = data.get("mint", "")
    sol_amount = float(data.get("solAmount", 0) or 0.0)

    if not wallet_addr or not mint or wallet_addr not in WALLET_MAP:
        return

    now = time.time()
    info = WALLET_MAP[wallet_addr]
    clusters[mint][wallet_addr] = {"time": now, "sol": sol_amount}
    cleanup_clusters(mint, now)

    active_kols = clusters[mint]
    count = len(active_kols)

    console.print(
        f"👀 [bold cyan]{info['name']} {info['emoji']}[/bold cyan] a acheté "
        f"[yellow]{sol_amount:.2f} SOL[/yellow] sur [green]{mint[:6]}...{mint[-4:]}[/green] "
        f"({count}/{REQUIRED_KOLS} pour consensus)"
    )

    if count >= REQUIRED_KOLS and mint not in tokens_bought:
        tokens_bought.add(mint)
        kol_details = [f"{WALLET_MAP[w]['name']} ({d['sol']:.2f} SOL)" for w, d in active_kols.items()]
        total_sol = sum(d["sol"] for d in active_kols.values())

        console.print(Panel(
            f"[bold green]🚨 SIGNAL RUNNER : CONSENSUS KOL ATTEINT ![/bold green]\n\n"
            f"Token (Mint) : [bold yellow]{mint}[/bold yellow]\n"
            f"KOLs         : {', '.join(kol_details)}\n"
            f"Volume KOLs  : [bold magenta]{total_sol:.2f} SOL[/bold magenta]",
            title="🎯 KOL CLUSTERING ENGINE", border_style="bright_green"
        ))

        paper_engine.execute_buy(
            contract_address=mint,
            ticker="KOL_RUNNER",
            price_usd=0.0001,
            mc_usd=5000.0,
            vol_usd=3000.0
        )

async def listen_pump_portal():
    uri = "wss://pumpportal.fun/api/data"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    chunk_size = 50

    while True:
        try:
            console.print(f"[cyan]📡 Connexion à PumpPortal via aiohttp...[/cyan]")
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.ws_connect(uri, heartbeat=20) as ws:
                    console.print(f"[bold green]✅ Handshake réussi ! Envoi des souscriptions ({len(TRACKED_KEYS)} wallets)...[/bold green]")

                    for i in range(0, len(TRACKED_KEYS), chunk_size):
                        chunk = TRACKED_KEYS[i:i + chunk_size]
                        await ws.send_str(json.dumps({
                            "method": "subscribeAccountTrade",
                            "keys": chunk
                        }))
                        await asyncio.sleep(0.04)

                    console.print(f"[bold green]🎯 {len(TRACKED_KEYS)} wallets actifs ! En attente de trades Pump.fun...[/bold green]\n")

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                if "message" in data:
                                    console.print(f"[dim cyan]Serveur : {data['message']}[/dim cyan]")
                                elif data.get("txType") == "buy":
                                    await process_buy_event(data)
                            except json.JSONDecodeError:
                                continue
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        except Exception as e:
            console.print(f"[bold red]⚠️ Erreur/Coupure ({type(e).__name__}: {e}). Reconnexion dans 3s...[/bold red]")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(listen_pump_portal())
