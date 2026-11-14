import json, os, time, re, aiohttp
from dotenv import load_dotenv
load_dotenv()

class ScoringEngine:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.narrative_file = os.path.join(self.base_dir, "data", "narrative_signals.json")
        self.buffer_file = os.path.join(self.base_dir, "data", "tg_buffer.json")
        self.tier1_file = os.path.join(self.base_dir, "data", "smart_wallets_tier1.json")
        self.ml_file = os.path.join(self.base_dir, "data", "ml_weights.json")

    def _load_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def _load_ml_data(self):
        return self._load_json(self.ml_file, {})

    async def _get_narrative_bonus(self, ticker: str, name: str) -> float:
        target = f"{ticker} {name}".lower().strip()
        signals = self._load_json(self.narrative_file, [])
        bonus = 0.0
        now = time.time()

        # 1. Lecture instantanée des signaux actifs (0 ms)
        for sig in signals:
            if not isinstance(sig, dict):
                continue
            keywords = [str(k).lower() for k in sig.get("keywords", []) if len(str(k)) >= 3]
            if keywords and any(k in target for k in keywords):
                bonus = max(bonus, float(sig.get("narrative_strength", 0)))

        if bonus > 0:
            return min(45.0, bonus)

        # 2. Fast-Track Gemini (timeout 1.8s) uniquement si le vrai ticker est connu
        if not ticker or ticker.startswith("PUMP_"):
            return 0.0
        history = self._load_json(self.buffer_file, [])
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not history or not gemini_key:
            return 0.0

        msgs = [str(m.get("text") if isinstance(m, dict) else m) for m in history[-25:]]
        joined = "\n".join(msgs)
        if ticker.lower() not in joined.lower() and (not name or name.lower() not in joined.lower()):
            return 0.0

        prompt = (
            f"Analyse ces messages Telegram crypto. Le token '{ticker}' ({name}) est-il mentionné "
            f"avec un catalyseur organique (sans shill coordonné) ? Réponds uniquement en JSON: "
            f'{{"narrative_strength": 0 à 45}}. Messages:\n{joined[:3000]}'
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.8)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        txt = data["candidates"][0]["content"]["parts"][0]["text"]
                        res = json.loads(txt)
                        return min(45.0, max(0.0, float(res.get("narrative_strength", 0))))
        except Exception:
            pass
        return 0.0

    async def calculate_score(self, mint, kols_involved, mc_usd, ml_data=None, ticker="", mint_name=""):
        t1_data = self._load_json(self.tier1_file, {"tier1": []})
        t1_addrs = {k.get("address") for k in t1_data.get("tier1", []) if isinstance(k, dict)}

        # 1. Score KOLs + Cluster (Plafond 55 pts si >=2 KOLs ou Tier 1 + Volume)
        base = 0.0
        total_sol = 0.0
        for kol, info in kols_involved.items():
            sol = float(info.get("sol", 0.0)) if isinstance(info, dict) else 0.1
            total_sol += sol
            base += 28.0 if kol in t1_addrs else 15.0
            if sol >= 1.5:
                base += 8.0

        if len(kols_involved) >= 2:
            base += 15.0  # Bonus Consensus Cluster
        base = min(55.0, base)

        # 2. Bonus Narrative IA (0 à 45 pts)
        narrative = await self._get_narrative_bonus(ticker, mint_name)

        # 3. Calibration ML (Uniquement après >= 30 trades sur le bracket)
        mod = 0.0
        if ml_data:
            b = "Micro" if mc_usd < 100_000 else ("Low" if mc_usd < 500_000 else "Mid")
            stats = ml_data.get(b, {})
            cnt = int(stats.get("count", stats.get("trades", 0)))
            wr = float(stats.get("winrate", 0.0))
            if cnt >= 30:
                if wr >= 55.0: mod = 10.0
                elif wr <= 30.0: mod = -10.0

        return round(float(min(100.0, max(0.0, base + narrative + mod))), 1)

    def get_dynamic_sizing(self, score: float, base_size: float = 0.1) -> float:
        if score >= 85.0:
            return round(base_size * 2.0, 4)
        elif score >= 70.0:
            return round(base_size * 1.5, 4)
        return round(base_size, 4)
