#!/usr/bin/env python3
"""Configuration du trading bot - charges .env si existe."""
import os
from pathlib import Path

ENV_FILE = Path("/home/kilpi/trading_bot/.env")


def load_env_vars():
    """Charge les variables d'environnement depuis le fichier .env local ou systématiques."""
    env_vars = {}
    
    # Si .env existe, le charge
    if ENV_FILE.exists():
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    
    # Variables par défaut si pas dans .env
    defaults = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHANNEL_ID": os.getenv("TELEGRAM_CHANNEL_ID", "-1002156789012"),
    }
    
    for key, default in defaults.items():
        if key not in env_vars:
            env_vars[key] = default
    
    return env_vars


# Charger les variables au démarrage
env_vars = load_env_vars()

TELEGRAM_BOT_TOKEN = env_vars.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = env_vars.get("TELEGRAM_CHANNEL_ID", "-1002156789012")


if not TELEGRAM_BOT_TOKEN:
    print("[CONFIG] Warning: TELEGRAM_BOT_TOKEN non configuré !")
