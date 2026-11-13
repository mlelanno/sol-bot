import json
import os
from pathlib import Path

BASE_DIR = "/home/kilpi/trading_bot"
CONFIG_FILE = os.path.join(BASE_DIR, "data", "bot_config.json")

DEFAULT_CONFIG = {
    "bot_paused": False,
    "min_score": 60,
    "trade_size_sol": 0.1,
    "stop_loss_pct": -25.0,
    "take_profit_pct": 60.0,
}


class ConfigManager:
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = DEFAULT_CONFIG.copy()
        self._load()

    def _load(self):
        """Charge la configuration depuis le fichier JSON."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                    # Merge: only override keys that exist in loaded dict
                    for key in DEFAULT_CONFIG:
                        if key in loaded:
                            self.config[key] = loaded[key]
        except (json.JSONDecodeError, Exception):
            # En cas d'erreur, on garde les valeurs par défaut
            pass

    def save(self):
        """Sauvegarde la configuration actuelle dans le fichier JSON."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)

    def load_config(self) -> dict:
        """Renvoie la configuration actuelle."""
        return self.config.copy()

    def update_config(self, updates: dict):
        """Met à jour une ou plusieurs clés de la configuration."""
        for key, value in updates.items():
            if key in self.config:
                self.config[key] = value
        self.save()

    def get(self, key: str, default=None):
        """Accès pratique à une seule clé."""
        return self.config.get(key, default)