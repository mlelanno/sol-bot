"""Minimal FastAPI dashboard for Quant Terminal."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from pydantic import BaseModel
import json

BASE_DIR = "/home/kilpi/trading_bot"
TRADES_FILE = os.path.join(BASE_DIR, "logs/paper_trades.json")
POSITIONS_FILE = os.path.join(BASE_DIR, "data/active_positions.json")
ML_WEIGHTS_FILE = os.path.join(BASE_DIR, "data/ml_weights.json")
TIER1_FILE = os.path.join(BASE_DIR, "data/smart_wallets_tier1.json")
NARRATIVE_FILE = os.path.join(BASE_DIR, "data/narrative_signals.json")
AUDIT_FILE = os.path.join(BASE_DIR, "logs/narrative_audit.jsonl")
REJECTED_FILE = os.path.join(BASE_DIR, "logs/rejected_tokens.jsonl")

class StateResponse(BaseModel):
    metrics: dict
    active_positions: list
    rejected_tokens: list
    narrative: dict
    tier1_wallets: list
    ml_weights: dict

app = FastAPI(title="Quant Terminal Dashboard", description="Fintech Terminal API")


@app.get("/api/state", response_model=StateResponse)
async def api_state():
    def load_json(path, default=None):
        try:
            with open(path) as f:
                data = json.load(f)
            return data if data is not None else default
        except Exception:
            return default

    trades = load_json(TRADES_FILE, [])
    sells = [t for t in trades if t.get("action") == "SELL" and t.get("pnl_sol") is not None]
    pnl_vals = [t["pnl_sol"] for t in sells]
    wins = [v for v in pnl_vals if v > 0]
    losses = [v for v in pnl_vals if v < 0]
    total = len(sells)
    winrate = (len(wins) / total * 100) if total else 0.0
    total_pnl = sum(pnl_vals)
    total_profit = sum(v for v in pnl_vals if v > 0)
    total_loss = abs(sum(v for v in pnl_vals if v < 0))
    pf = total_profit / total_loss if total_loss else (float("inf") if total_profit > 0 else 0.0)
    cap = 2.0; peak = 2.0; max_dd_sol = 0.0; max_dd_pct = 0.0
    for t in trades:
        if t.get("action") == "BUY" and t.get("amount_sol"): cap -= t["amount_sol"]
        elif t.get("action") == "SELL" and t.get("pnl_sol") is not None: cap += t["pnl_sol"]
        if cap > peak: peak = cap
        if cap < peak: dd = peak - cap; max_dd_sol = max(max_dd_sol, dd); max_dd_pct = max(max_dd_pct, dd / peak * 100) if peak else 0
    active = load_json(POSITIONS_FILE, {})
    return {
        "metrics": {
            "balance": "2.0000",
            "total_pnl_sol": fmt(total_pnl),
            "winrate_pct": fmt(winrate),
            "profit_factor": fmt(pf),
            "max_drawdown_sol": fmt(max_dd_sol),
            "max_drawdown_pct": fmt(max_dd_pct),
            "total_trades": total,
            "active_positions": len(active),
        },
        "active_positions": [],
        "rejected_tokens": [],
        "narrative": {"active": [], "audit": []},
        "tier1_wallets": [],
        "ml_weights": {},
    }


def fmt(x, d=4): return f"{x:.{d}f}"