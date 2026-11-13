import json
import os
import time

ML_WEIGHTS_FILE = "/home/kilpi/trading_bot/data/ml_weights.json"
NARRATIVE_SIGNALS_FILE = "/home/kilpi/trading_bot/data/narrative_signals.json"

MC_BRACKET_BOUNDS = {
    "Micro": (0, 1_000_000),
    "Low": (1_000_000, 10_000_000),
    "Mid": (10_000_000, float("inf")),
}

# TTL narratif : 30 minutes
NARRATIVE_TTL = 1800


class ScoringEngine:
    def __init__(self):
        self.ml_weights_file = ML_WEIGHTS_FILE
        self.narrative_signals_file = NARRATIVE_SIGNALS_FILE

    def _load_ml_data(self):
        try:
            with open(self.ml_weights_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"mc_brackets_stats": {}}

    def _load_narrative_signals(self):
        try:
            if not os.path.exists(self.narrative_signals_file):
                return []
            with open(self.narrative_signals_file, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, Exception):
            return []

    def _get_mc_bracket(self, mc_usd: float) -> str:
        for bracket, (lower, upper) in MC_BRACKET_BOUNDS.items():
            if lower <= mc_usd < upper:
                return bracket
        return "Mid"

    def _is_narrative_valid(self, signal: Dict[str, Any]) -> bool:
        """Vérifie si le signal narratif est toujours valide (TTL 30min)."""
        ts = signal.get("timestamp", 0)
        if ts == 0:
            return True
        if isinstance(ts, str):
            try:
                ts = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                return True
        if time.time() - ts > NARRATIVE_TTL:
            return False
        return True

    async def get_active_narrative_score(self, ticker: str, mint_name: str = "") -> int:
        """Recherche les signaux narratifs actifs et calcule le score max 45 pts."""
        signals = self._load_narrative_signals()
        if not signals:
            return 0

        # Construire les mots-clés de recherche à partir du ticker et du nom
        search_terms = set()
        ticker_upper = (ticker or "").upper()
        if ticker_upper:
            # Extraire les symboles après le $ ou les parties alphanumériques
            import re
            search_terms.add(ticker_upper)
            search_terms.add(ticker_upper.replace("$", ""))
            for part in ticker_upper.split("_"):
                if part:
                    search_terms.add(part)

        if mint_name:
            search_terms.add(mint_name.upper())

        max_signal_score = 0

        for signal in signals:
            if not self._is_narrative_valid(signal):
                continue

            narrative_text = (signal.get("text") or "").upper()
            if not narrative_text:
                continue

            matched_term = None
            for term in search_terms:
                if term and term in narrative_text:
                    matched_term = term
                    break

            if not matched_term:
                continue

            # Seuls les signaux organiques comptent (pas le shill coordonné)
            is_organic = signal.get("is_organic", False)
            shill_pattern = signal.get("shill_pattern", False)
            if not is_organic or shill_pattern:
                continue

            narrative_strength = int(signal.get("narrative_strength", 0))
            # Score proportionnel : 45 pts max pour narrative_strength 100
            signal_score = int(45 * narrative_strength / 100.0)
            max_signal_score = max(max_signal_score, signal_score)

        return max_signal_score

    async def calculate_score(self, mint, kols_involved, mc_usd, ml_data=None):
        """Calcule un score composite de conviction pour un token (100 pts max).

        Règles :
        - Poids Wallets Tier 1 : +17.5 pts par wallet (max 35 pts)
        - Narrative actif : max 45 pts (vieux : kols KOLs)
        - Vélocité : +10 pts si < 10s
        - Validation ML : +10 pts ou -50 pts si tranche toxique (>= 30 trades)
        """
        score = 0.0

        # Poids Wallets Tier 1 : +17.5 pts par wallet (max 35 pts)
        wallet_count = len(kols_involved)
        score += min(wallet_count * 17.5, 35)

        # Bonus Narrative actif : max 45 pts
        # NOTE: dans le flux actual, `mint` contient le token identifié par narrative
        narrative_score = await self.get_active_narrative_score(mint, "N/A")
        score += min(narrative_score, 45)

        # Bonus de vélocité : +10 pts si < 10s
        times = [v.get("time", 0) for v in kols_involved.values() if v.get("time", 0) > 0]
        if len(times) >= 2 and (max(times) - min(times)) < 10:
            score += 10

        # Poids Machine Learning
        if ml_data is None:
            ml_data = self._load_ml_data()

        brackets_stats = ml_data.get("mc_brackets_stats", {})
        bracket = self._get_mc_bracket(mc_usd)
        bracket_stats = brackets_stats.get(bracket, {})
        winrate = bracket_stats.get("winrate", 0.0)
        bracket_count = bracket_stats.get("count", 0)

        if bracket_count >= 30:
            if winrate > 45.0:
                score += 10
            else:
                score -= 50
        else:
            # Données insuffisantes, pas de pénalité forte
            score += 10

        return score

    def get_dynamic_sizing(self, score):
        """Retourne la taille de position en SOL selon le score (100 pts)."""
        if score < 60:
            return 0.0
        elif 60 <= score < 75:
            return 0.03
        elif 75 <= score < 90:
            return 0.05
        else:
            return 0.08