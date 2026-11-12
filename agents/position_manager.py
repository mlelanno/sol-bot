#!/usr/bin/env python3
"""Position Manager - Surveillance des positions trading avec stop-loss et take-profit."""

import asyncio
import aiohttp
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

BASE_DIR = "/home/kilpi/trading_bot"
ACTIVE_POSITIONS_FILE = os.path.join(BASE_DIR, "data", "active_positions.json")
PAPER_TRADES_FILE = os.path.join(BASE_DIR, "logs", "paper_trades.json")
TELEGRAM_BOT_TOKEN_FILE = os.path.join(BASE_DIR, ".env")
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens"

CHECK_INTERVAL = 10


def load_env() -> dict:
    env_vars = {}
    if os.path.exists(TELEGRAM_BOT_TOKEN_FILE):
        with open(TELEGRAM_BOT_TOKEN_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"\'')
    return env_vars


async def fetch_price(mint_address: str, session: aiohttp.ClientSession) -> float | None:
    try:
        url = f"{DEXSCREENER_API_URL}/{mint_address}"
        async with session.get(url, timeout=4) as response:
            if response.status == 200:
                data = await response.json()
                pairs = data.get("pairs", [])
                if pairs and len(pairs) > 0:
                    return float(pairs[0].get("priceUsd", 0))
    except Exception as e:
        print(f"[WARN] Erreur fetch prix pour {mint_address[:8]}... : {type(e).__name__}")
    return None


async def send_telegram(message: str) -> bool:
    import urllib.parse
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    
    if not token or not channel_id:
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data={
                "chat_id": channel_id, 
                "text": message, 
                "parse_mode": "HTML"
            }) as response:
                return response.status == 200
    except Exception:
        pass
    return False


def load_positions() -> dict:
    try:
        with open(ACTIVE_POSITIONS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_positions(positions: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(ACTIVE_POSITIONS_FILE), exist_ok=True)
        with open(ACTIVE_POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] Sauvegarde échouée : {e}")
        return False


def append_trade(trade_record: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(PAPER_TRADES_FILE), exist_ok=True)
        with open(PAPER_TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(PAPER_TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Ajout trade échoué : {e}")
        return False
    return True
async def process_position(mint_address: str, current_price: float) -> dict | None:
    positions = load_positions()
    
    if mint_address not in positions:
        print(f"[WARN] {mint_address[:8]}... pas trouvé dans les positions actives")
        return None
    
    position = positions[mint_address]
    entry_price_usd = float(position.get("entry_price_usd", 0))
    tokens_held = float(position.get("tokens_held", 0)) or float(position.get("tokens", 0))
    tp1_executed = bool(position.get("tp1_executed", False))
    
    if entry_price_usd <= 0:
        print(f"[ERROR] Prix d'entrée invalide pour {mint_address[:8]}... ({entry_price_usd})")
        return None
    
    pnl_pct = ((current_price - entry_price_usd) / entry_price_usd) * 100
    action_type = None
    trade_record = None
    
    # Stop-loss (-30%) : VENT 100% + suppression
    if pnl_pct <= -30.0:
        action_type = "STOP_LOSS"
        tokens_to_sell = tokens_held
        sell_sol = tokens_to_sell * current_price
        trade_record = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",
            "action": "SELL",
            "reason": "STOP-LOSS (-30%)",
            "mint": mint_address,
            "current_price_usd": current_price,
            "entry_price_usd": entry_price_usd,
            "pnl_pct": round(pnl_pct, 2),
            "tokens_sold": round(tokens_to_sell, 6),
            "sell_sol": round(sell_sol, 4)
        }
    
    # Take-Profit 1 (+100%) si pas exécuté : VENT 50%
    elif pnl_pct >= 100.0 and not tp1_executed:
        action_type = "TAKE_PROFIT_1"
        tokens_to_sell = tokens_held / 2.0
        sell_sol = tokens_to_sell * current_price
        new_tokens_held = tokens_held - tokens_to_sell
        trade_record = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",
            "action": "SELL_PARTIAL",
            "reason": "TAKE-PROFIT 1 (+100%) - 50% vendus",
            "mint": mint_address,
            "current_price_usd": current_price,
            "entry_price_usd": entry_price_usd,
            "pnl_pct": round(pnl_pct, 2),
            "tokens_sold": round(tokens_to_sell, 6),
            "sell_sol": round(sell_sol, 4)
        }
        
        if action_type == "TAKE_PROFIT_1" and new_tokens_held > 0:
            old_position = positions[mint_address]
            remaining_tokens = new_tokens_held
            new_entry_price = round(
                (tokens_to_sell * current_price + entry_price_usd * remaining_tokens) / 
                (remaining_tokens + 1e-9), 6
            ) if remaining_tokens > 0 else current_price
            
            old_position["tokens"] = remaining_tokens
            old_position["entry_price_usd"] = new_entry_price
            old_position["tp1_executed"] = True
            positions[mint_address] = old_position
            
            trade_record["current_position"] = {
                "tokens": remaining_tokens,
                "entry_price_usd": new_entry_price
            }
    
    # Take-Profit 2 (+300%) : VENT 100% des restants
    elif pnl_pct >= 300.0:
        action_type = "TAKE_PROFIT_2"
        tokens_to_sell = tokens_held
        sell_sol = tokens_to_sell * current_price
        trade_record = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",
            "action": "SELL",
            "reason": "TAKE-PROFIT 2 (+300%) - Clôture totale",
            "mint": mint_address,
            "current_price_usd": current_price,
            "entry_price_usd": entry_price_usd,
            "pnl_pct": round(pnl_pct, 2),
            "tokens_sold": round(tokens_to_sell, 6),
            "sell_sol": round(sell_sol, 4)
        }
    
    if not trade_record:
        print(f"[INFO] Aucune action pour {mint_address[:8]}... (P&L={pnl_pct:.2f}%)")
        return None
    
    # Construire le message Telegram
    remaining_tokens = new_tokens_held if action_type in ("TAKE_PROFIT_1",) else 0

    if action_type == "STOP_LOSS":
        pnl_pct_val = round(pnl_pct, 2)
        msg = f"<b>🛑 STOP-LOSS DÉCLANCHÉ</b>\n\n"
        msg += f"<b>Prix cible:</b> {current_price:.6f} USD ({pnl_pct_val}% {'perte' if pnl_pct_val < 0 else 'gain'})\n"
        msg += f"<b>Raison:</b> {trade_record['reason']}\n\n"
        msg += f"<b>💰 Réalisé :</b>\n"
        msg += f"• Vendu : {tokens_to_sell} tokens ({sell_sol:.4f} SOL)\n"
        msg += f"{mint_address[:8]}...\n\n"
        
        if remaining_tokens > 0:
            new_entry_price = round(
                (tokens_to_sell * current_price + entry_price_usd * remaining_tokens) / 
                (remaining_tokens + 1e-9), 6
            )
            
            old_position = positions[mint_address]
            old_position["tokens"] = remaining_tokens
            old_position["entry_price_usd"] = new_entry_price
            
            msg += f"<b>📊 Position restante :</b>\n"
            msg += f"• {remaining_tokens} tokens à {new_entry_price:.6f} USD\n"
    
    elif action_type == "TAKE_PROFIT_1":
        if remaining_tokens > 0:
            new_entry_price = round(
                (tokens_to_sell * current_price + entry_price_usd * remaining_tokens) / 
                (remaining_tokens + 1e-9), 6
            )
            
            old_position = positions[mint_address]
            old_position["tokens"] = remaining_tokens
            old_position["entry_price_usd"] = new_entry_price
            old_position["tp1_executed"] = True
            
        msg = f"<b>✅ TAKE-PROFIT 1 ACTIF</b>\n\n"
        msg += f"<b>Objectif:</b> +100% ✅\n\n"
        msg += f"<b>Raison:</b> {trade_record['reason']}\n\n"
        msg += f"<b>💰 Réalisé :</b>\n"
        msg += f"• Vendu : {tokens_to_sell} tokens ({sell_sol:.4f} SOL)\n"
        msg += f"{mint_address[:8]}...\n\n"
        
        if remaining_tokens > 0:
            msg += f"<b>📊 Position restante :</b>\n"
            msg += f"• {remaining_tokens} tokens à {new_entry_price:.6f} USD\n"
    
    elif action_type == "TAKE_PROFIT_2":
        msg = f"<b>✅ TAKE-PROFIT 2 ACTIF</b>\n\n"
        msg += f"<b>Objectif:</b> +300% ✅\n\n"
        msg += f"<b>💰 Réalisé :</b>\n"
        msg += f"• Vendu : {tokens_to_sell} tokens ({sell_sol:.4f} SOL)\n"
        msg += f"{mint_address[:8]}...\n\n"
    
    if action_type:
        mint_short = f"{mint_address[:8]}...{mint_address[-4]}"
        print(f"[INFO] Trade enregistré pour {mint_short} : {action_type}")
        
        trade_record["telegram_msg"] = msg
    
    # Sauvegarder le trade
    append_trade(trade_record)
    
    # Retirer la position du dictionnaire si elle est totalement vendue (STOP_LOSS ou TAKE_PROFIT_2)
    # pour éviter la boucle infinie de ré-écriture des positions terminées
    if action_type in ["STOP_LOSS", "TAKE_PROFIT_2"]:
        del positions[mint_address]
    
    return trade_record


async def run_position_manager(check_interval: int = 10) -> None:
    """Fonction principale pour surveiller et gérer les positions."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                print(f"[INFO] Chargement des positions actives...")
                
                positions = load_positions()
                
                if not positions or len(positions) == 0:
                    print("[INFO] Aucune position active - surveillance en attente...")
                    await asyncio.sleep(check_interval)
                    continue
                
                print(f"[INFO] {len(positions)} position(s) active(s) à surveiller")
                
                for mint_address, position in positions.items():
                    price = await fetch_price(mint_address, session)
                    
                    if price is None:
                        print(f"[WARN] Timeout après 4s - ignoring {mint_address[:8]}... pour ce cycle")
                        continue
                    
                    pnl_pct = ((price - float(position.get("entry_price_usd", 0))) / 
                               float(position.get("entry_price_usd", 1))) * 100
                    
                    await process_position(mint_address, price)
                
                save_positions(positions)
                
                elapsed = time.time() - time.monotonic_start if hasattr(time, 'monotonic_start') else 0
                remaining = check_interval - (elapsed % check_interval)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    
            except KeyboardInterrupt:
                print("[INFO] Position Manager arrêté par l'utilisateur")
                break
            except Exception as e:
                print(f"[ERROR] Erreur critique : {type(e).__name__} - {e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(run_position_manager(check_interval=10))
    except Exception as e:
        print(f"[FATAL] Erreur fatale : {type(e).__name__} - {e}")
        sys.exit(1)