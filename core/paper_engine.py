import json, os, random, asyncio
from datetime import datetime

class PaperTradingEngine:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.pos_file = os.path.join(self.base_dir, "data", "active_positions.json")
        self.trades_file = os.path.join(self.base_dir, "logs", "paper_trades.json")

    def _atomic_save(self, path, data):
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    async def execute_buy(self, contract_address, ticker, price_usd, mc_usd, vol_usd, trade_size, kols, score=60.0):
        delay_s = random.uniform(0.010, 0.050)
        await asyncio.sleep(delay_s)

        try:
            pos = json.load(open(self.pos_file, encoding="utf-8"))
            if isinstance(pos, list):
                pos = {x.get("mint") or x.get("contract_address"): x for x in pos if isinstance(x, dict)}
        except Exception:
            pos = {}

        # 1. Anti-doublon
        if contract_address in pos:
            return False, "Position déjà ouverte"

        # 2. Vérification du capital disponible (Base 2.0 SOL)
        locked_sol = sum(float(p.get("invested_sol", p.get("trade_size", 0.1))) for p in pos.values())
        if locked_sol + trade_size > 2.0:
            return False, "Capital SOL disponible insuffisant"

        # 3. Modélisation réaliste du slippage d'entrée selon MC + Tip Jito
        slippage_pct = 0.08 if mc_usd < 50_000 else (0.05 if mc_usd < 250_000 else 0.03)
        jito_tip = 0.0015
        executed_price = price_usd * (1.0 + slippage_pct)
        invested = round(trade_size - jito_tip, 4)
        if invested <= 0:
            return False, "Taille inférieure au tip Jito"

        now_iso = datetime.now().isoformat()
        pos[contract_address] = {
            "mint": contract_address,
            "ticker": ticker,
            "entry_price": executed_price,
            "current_price": executed_price,
            "mc_usd": mc_usd,
            "invested_sol": invested,
            "trade_size": trade_size,
            "pnl_pct": 0.0,
            "score": score,
            "opened_at": time.time() if "time" in globals() else __import__("time").time(),
            "kols": kols
        }
        self._atomic_save(self.pos_file, pos)

        try:
            trades = json.load(open(self.trades_file, encoding="utf-8"))
            if not isinstance(trades, list): trades = []
        except Exception:
            trades = []

        rec = {
            "timestamp": now_iso,
            "action": "BUY",
            "contract_address": contract_address,
            "ticker": ticker,
            "price_usd": executed_price,
            "mc_usd": mc_usd,
            "trade_size": invested,
            "tip_sol": jito_tip,
            "slippage_pct": round(slippage_pct * 100, 1),
            "latency_ms": round(delay_s * 1000, 1),
            "score": score,
            "kols": kols
        }
        trades.append(rec)
        self._atomic_save(self.trades_file, trades)
        return True, rec
