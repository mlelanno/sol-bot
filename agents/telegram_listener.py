import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import re
import aiohttp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
    PUMP_MIN_VOLUME_USD,
    PUMP_MIN_MARKET_CAP_USD
)
from core.power import is_gpu_ready, wake_gpu_server
from core.paper_engine import paper_engine

console = Console()
router = Router()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

SOLANA_CONTRACT_REGEX = re.compile(r"\b[1-9A-HJ-NP-za-km-z]{32,44}\b")
TICKER_REGEX = re.compile(r"\$([A-Za-z0-9_]+)")

def is_target_channel(message: Message) -> bool:
    return str(message.chat.id) == str(TELEGRAM_CHANNEL_ID)

async def check_dexscreener_metrics(contract_address: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                pairs = data.get("pairs")
                if not pairs:
                    return None
                pair = pairs[0]
                return {
                    "price_usd": float(pair.get("priceUsd", 0) or 0),
                    "volume_usd": float(pair.get("volume", {}).get("h24", 0) or 0),
                    "market_cap": float(pair.get("fdv", 0) or pair.get("marketCap", 0) or 0)
                }
    except Exception as e:
        console.print(f"[bold red]Erreur Dexscreener : {e}[/bold red]")
        return None

async def inject_into_pipeline(contract_address: str, ticker: str = ""):
    console.print(f"\n[cyan]🔍 Interrogation de Dexscreener pour {contract_address}...[/cyan]")
    metrics = await check_dexscreener_metrics(contract_address)

    if not metrics:
        console.print(Panel(
            f"[bold yellow]Contrat : {contract_address}\nAucune paire active trouvée sur Dexscreener (Token probablement trop récent ou non indexé).[/bold yellow]",
            title="⚠️ FILTRE DEXSCREENER", border_style="yellow"
        ))
        return

    mc = metrics["market_cap"]
    vol = metrics["volume_usd"]
    price = metrics["price_usd"]

    table = Table(title="Métriques du Token")
    table.add_column("Métrique", style="bold")
    table.add_column("Valeur Réelle", style="yellow")
    table.add_column("Critère Minimum", style="magenta")
    table.add_row("Market Cap", f"${mc:,.2f}", f"${PUMP_MIN_MARKET_CAP_USD:,.2f}")
    table.add_row("Volume", f"${vol:,.2f}", f"${PUMP_MIN_VOLUME_USD:,.2f}")
    console.print(table)

    if mc < PUMP_MIN_MARKET_CAP_USD or vol < PUMP_MIN_VOLUME_USD:
        console.print(f"[bold red]⛔ SKIP : Critères non atteints (MC: ${mc:.0f}, Vol: ${vol:.0f})[/bold red]")
        return

    console.print(f"[bold green] Conditions validées ! Déclenchement du Paper Trade...[/bold green]")
    success, trade = paper_engine.execute_buy(
        contract_address=contract_address,
        ticker=ticker,
        price_usd=price,
        mc_usd=mc,
        vol_usd=vol
    )

    if success:
        console.print(Panel(
            f"[bold green]ACHAT SIMULÉ EFFECTUÉ ![/bold green]\n"
            f"Token : {ticker} ({contract_address})\n"
            f"Montant : {trade['amount_sol']} SOL\n"
            f"Prix exécuté : ${trade['executed_price_usd']:.8f} (Slippage: 15%)\n"
            f"Solde restant : {trade['remaining_sol']} SOL",
            title="💰 PAPER TRADING ENGINE", border_style="green"
        ))
    else:
        console.print(f"[bold red]Erreur Paper Trading : {trade}[/bold red]")

@router.channel_post(is_target_channel)
async def handle_channel_post(message: Message):
    text = message.text or message.caption or ""
    contracts = SOLANA_CONTRACT_REGEX.findall(text)
    tickers = TICKER_REGEX.findall(text)

    if not contracts:
        return

    ca = contracts[0]
    ticker = f"${tickers[0]}" if tickers else "$UNKNOWN"

    gpu_online = await is_gpu_ready()
    status_gpu = "[bold green]EN LIGNE[/bold green]" if gpu_online else "[bold yellow]WOL ENVOYÉ[/bold yellow]"
    if not gpu_online:
        wake_gpu_server()

    console.print(Panel(
        f"Contrat Solana : [bold yellow]{ca}[/bold yellow]\n"
        f"Ticker Détecté : [bold cyan]{ticker}[/bold cyan]\n"
        f"Statut GPU     : {status_gpu}",
        title="🚨 SENTINELLE TELEGRAM", border_style="red"
    ))

    await inject_into_pipeline(ca, ticker)

async def main():
    console.print(f"[bold green]🚀 Sentinelle en écoute sur le canal {TELEGRAM_CHANNEL_ID}...[/bold green]")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
