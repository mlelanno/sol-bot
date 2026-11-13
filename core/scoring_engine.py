import json
import os

ML_WEIGHTS_FILE = "/home/kilpi/trading_bot/data/ml_weights.json"

MC_BRACKET_BOUNDS = {
    "Micro": (0, 1_000_000),
    "Low": (1_000_000, 10_000_000),
    "Mid": (10_000_000, float("inf")),
}


class ScoringEngine:
    def __init__(self):
        self.ml_weights_file = ML_WEIGHTS_FILE

    def _load_ml_data(self):
        try:
            with open(self.ml_weights_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"mc_brackets_stats": {}}

    def _get_mc_bracket(self, mc_usd: float) -> str:
        for bracket, (lower, upper) in MC_BRACKET_BOUNDS.items():
            if lower <= mc_usd < upper:
                return bracket
        return "Mid"

    async def calculate_score(self, mint, kols_involved, mc_usd, ml_data=None):
        """Calcule un score composite de conviction pour un token.

        Règles :
        - KOLs : +15 pts par KOL (max 45)
        - ML : +35 si winrate > 45%, +15 si 30-45%, -50 si < 30%
        - Vélocité : +20 si tous les achats en < 10s
        """
        score = 0.0

        # Poids KOLs (max 45 pts)
        kol_count = len(kols_involved)
        score += min(kol_count * 15, 45)

        # Bonus de vélocité (max 20 pts)
        times = [v["time"] for v in kols_involved.values() if "time" in v]
        if times and (max(times) - min(times)) < 10:
            score += 20

        # Poids Machine Learning
        if ml_data is None:
            ml_data = self._load_ml_data()

        brackets_stats = ml_data.get("mc_brackets_stats", {})
        bracket = self._get_mc_bracket(mc_usd)
        bracket_stats = brackets_stats.get(bracket, {})
        winrate = bracket_stats.get("winrate", 0.0)

        if winrate > 45.0:
            score += 35
        elif 30.0 <= winrate <= 45.0:
            score += 15
        else:
            score -= 50

        return score

    def get_dynamic_sizing(self, score):
        """Retourne la taille de position en SOL selon le score."""
        if score < 60:
            return 0.0
        elif 60 <= score < 75:
            return 0.03
        elif 75 <= score < 90:
            return 0.05
        else:
            return 0.08