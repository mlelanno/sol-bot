import asyncio
import json
import os
import time
from pathlib import Path

# IGNORED_MINTS: Tokens que le bot doit ignorer pour éviter d'acheter des faux jetons
IGNORED_MINTS = {
    "So11111111111111111111111111111111111111112",  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",  # NVDAx
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # JitoSOL
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",  # bSOL
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # RAY
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "data", "bot_config.json")
REJECTS_FILE = os.path.join(BASE_DIR, "logs", "rejected_tokens.jsonl")


def load_live_config():
    """Charge la configuration live depuis bot_config.json avec valeurs par défaut."""
    default_cfg = {
        "bot_paused": False,
        "min_score": 60,
        "trade_size_sol": 0.1,
        "stop_loss_pct": -25.0,
        "take_profit_pct": 60.0,
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**default_cfg, **json.load(f)}
    except Exception:
        pass
    return default_cfg


def log_rejection(mint, ticker, name, score, mc_usd, reason):
    """Enregistre un token rejeté dans logs/rejected_tokens.jsonl."""
    bracket = "Micro" if mc_usd < 100_000 else ("Low" if mc_usd < 500_000 else "Mid")
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mint": mint,
        "ticker": ticker,
        "name": name,
        "score": round(float(score or 0), 1),
        "mc_bracket": bracket,
        "reason": str(reason),
    }
    try:
        lines = []
        if os.path.exists(REJECTS_FILE):
            with open(REJECTS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()[-199:]
        lines.append(json.dumps(entry) + "\n")
        with open(REJECTS_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


# Point d'entrée pour l'écouteur Helius
async def process_new_token(mint, ticker, name, score, mc_usd, reason):
    """Traite un nouveau token détecté par Helius.
    
    Filtre les mints ignorés et enregistre les rejets.
    """
    # Filtrer les mints ignorés (WSOL, USDC, USDT, tokens connus de shill)
    if mint in IGNORED_MINTS:
        return

    # Vérifier si le bot est en pause
    config = load_live_config()
    if config.get("bot_paused", False):
        return

    # Enregistrer le rejet
    log_rejection(mint, ticker, name, score, mc_usd, reason)

    # TODO: Ajouter ici la logique d'achat après filtrage
    # Le bot n'achètera pas les tokens dans IGNORED_MINTS


# Si ce fichier est exécuté directement, démarrer l'écouteur
if __name__ == "__main__":
    print("Helius Listener en cours d'exécution...")
    print(f"Ignorés {len(IGNORED_MINTS)} mints: {', '.join(IGNORED_MINTS)}")
    config = load_live_config()
    print(f"Configuration: {config}")