import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(DATA_DIR, "bot_config.json")
POSITIONS_PATH = os.path.join(DATA_DIR, "active_positions.json")
TRADES_PATH = os.path.join(LOGS_DIR, "paper_trades.json")
REJECTS_PATH = os.path.join(LOGS_DIR, "rejected_tokens.jsonl")
NARRATIVE_SIGNALS_PATH = os.path.join(DATA_DIR, "narrative_signals.json")
NARRATIVE_AUDIT_PATH = os.path.join(LOGS_DIR, "narrative_audit.jsonl")
TIER1_PATH = os.path.join(DATA_DIR, "smart_wallets_tier1.json")
FALLBACK_WALLETS_PATH = os.path.join(DATA_DIR, "smart_wallets.json")
ML_WEIGHTS_PATH = os.path.join(DATA_DIR, "ml_weights.json")
HTML_PATH = os.path.join(BASE_DIR, "tools", "dashboard.html")

DEFAULT_CONFIG = {
    "bot_paused": False,
    "min_score": 60,
    "trade_size_sol": 0.1,
    "stop_loss_pct": -25.0,
    "take_profit_pct": 60.0
}

app = FastAPI(title="Quant Terminal PRO")

def read_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def read_jsonl(path: str, limit: int = 40) -> List[Dict[str, Any]]:
    items = []
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines[-limit:]):
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        pass
    return items

def load_config() -> Dict[str, Any]:
    cfg = read_json(CONFIG_PATH, {})
    merged = {**DEFAULT_CONFIG, **(cfg if isinstance(cfg, dict) else {})}
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
    return merged

def compute_metrics_and_trades():
    raw_trades = read_json(TRADES_PATH, [])
    if not isinstance(raw_trades, list):
        raw_trades = []

    buys_by_mint = {}
    closed_trades = []
    total_pnl_sol = 0.0
    total_fees_sol = 0.0
    wins = 0
    gross_profit = 0.0
    gross_loss = 0.0

    equity = 2.0
    peak = 2.0
    max_dd_sol = 0.0
    max_dd_pct = 0.0

    for t in raw_trades:
        if not isinstance(t, dict):
            continue
        action = str(t.get("action") or t.get("type") or "").upper()
        mint = t.get("contract_address") or t.get("mint") or t.get("token_address") or ""
        fees = float(t.get("fees_sol", 0.0) or 0.0)
        total_fees_sol += fees

        if action == "BUY":
            buys_by_mint[mint] = t
        elif action == "SELL":
            buy_ref = buys_by_mint.get(mint, {})
            pnl_sol = float(t.get("pnl_sol", t.get("pnl", 0.0)) or 0.0)
            pnl_pct = float(t.get("pnl_pct", t.get("roi_pct", 0.0)) or 0.0)
            total_pnl_sol += pnl_sol

            if pnl_sol > 0:
                wins += 1
                gross_profit += pnl_sol
            elif pnl_sol < 0:
                gross_loss += abs(pnl_sol)

            equity += pnl_sol - fees
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd_sol:
                max_dd_sol = dd
                max_dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0

            closed_trades.append({
                "timestamp": t.get("timestamp") or t.get("time") or "",
                "mint": mint,
                "ticker": t.get("ticker") or buy_ref.get("ticker") or (f"PUMP_{mint[:4]}" if mint else "UNKNOWN"),
                "pnl_sol": round(pnl_sol, 4),
                "pnl_pct": round(pnl_pct, 2),
                "kols": t.get("kols") or buy_ref.get("kols") or [],
                "reason": t.get("reason") or t.get("exit_reason") or "SELL"
            })

    total_closed = len(closed_trades)
    winrate = round((wins / total_closed * 100.0), 1) if total_closed > 0 else 0.0
    pf = round((gross_profit / gross_loss), 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 0.0)
    sol_balance = round(2.0 + total_pnl_sol - total_fees_sol, 4)

    return {
        "sol_balance": sol_balance,
        "pnl_total": round(total_pnl_sol, 4),
        "pnl_pct": round((total_pnl_sol / 2.0) * 100.0, 2),
        "winrate": winrate,
        "profit_factor": pf,
        "max_dd_sol": round(max_dd_sol, 4),
        "max_dd_pct": round(max_dd_pct, 2),
        "total_closed": total_closed
    }, list(reversed(closed_trades[-30:]))

def format_active_positions():
    raw_pos = read_json(POSITIONS_PATH, {})
    positions = []
    if isinstance(raw_pos, dict):
        items = raw_pos.items()
    elif isinstance(raw_pos, list):
        items = [(p.get("mint") or p.get("contract_address", f"pos_{i}"), p) for i, p in enumerate(raw_pos) if isinstance(p, dict)]
    else:
        items = []

    for mint, p in items:
        if not isinstance(p, dict):
            continue
        entry = float(p.get("entry_price") or p.get("buy_price") or p.get("price_usd") or 0.0)
        current = float(p.get("current_price") or p.get("last_price") or entry or 0.0)
        pnl_pct = float(p.get("pnl_pct", 0.0) or 0.0)
        if pnl_pct == 0.0 and entry > 0 and current > 0:
            pnl_pct = ((current - entry) / entry) * 100.0
        invested = float(p.get("trade_size") or p.get("amount_sol") or p.get("invested_sol") or p.get("size_sol") or 0.05)
        positions.append({
            "mint": mint,
            "ticker": p.get("ticker") or p.get("symbol") or f"PUMP_{str(mint)[:4]}",
            "entry_price": entry,
            "current_price": current,
            "pnl_pct": round(pnl_pct, 2),
            "invested_sol": round(invested, 4),
            "score": p.get("score") or p.get("entry_score") or "-",
            "kols": p.get("kols") or []
        })
    return positions

def format_narratives():
    raw_signals = read_json(NARRATIVE_SIGNALS_PATH, [])
    if not isinstance(raw_signals, list):
        raw_signals = []
    now_ts = datetime.now(timezone.utc).timestamp()
    active_signals = []
    for s in raw_signals:
        if not isinstance(s, dict):
            continue
        ts_val = s.get("timestamp")
        sig_ts = 0.0
        if isinstance(ts_val, (int, float)):
            sig_ts = float(ts_val)
        elif isinstance(ts_val, str):
            try:
                dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                sig_ts = dt.timestamp()
            except Exception:
                sig_ts = now_ts
        elapsed = max(0.0, now_ts - sig_ts) if sig_ts > 0 else 0.0
        remaining = max(0, int(1800 - elapsed))
        if remaining > 0:
            active_signals.append({
                "keywords": s.get("keywords") or [],
                "narrative_strength": int(s.get("narrative_strength") or s.get("strength") or 0),
                "ttl_seconds": remaining,
                "ttl_pct": round((remaining / 1800.0) * 100, 1)
            })
    audits = read_jsonl(NARRATIVE_AUDIT_PATH, limit=20)
    return {"signals": active_signals, "audit": audits}

def format_tier1():
    raw = read_json(TIER1_PATH, None)
    if not raw:
        raw = read_json(FALLBACK_WALLETS_PATH, [])
    wallets = []
    if isinstance(raw, dict):
        raw = raw.get("wallets") or raw.get("tier1") or list(raw.values())
    if isinstance(raw, list):
        for idx, w in enumerate(raw[:30]):
            if isinstance(w, dict):
                addr = w.get("address") or w.get("wallet") or ""
                wallets.append({
                    "rank": idx + 1,
                    "address": addr,
                    "name": w.get("name") or w.get("label") or (f"{addr[:4]}...{addr[-4:]}" if len(addr) > 8 else addr),
                    "winrate": round(float(w.get("winrate", 0.0) or 0.0), 1),
                    "total_pnl": round(float(w.get("total_pnl_generated") or w.get("pnl_sol") or 0.0), 3),
                    "calls": int(w.get("total_calls") or w.get("calls") or w.get("trades") or 0)
                })
    return wallets

def format_ml_weights():
    raw = read_json(ML_WEIGHTS_PATH, {})
    brackets = raw.get("brackets") if isinstance(raw, dict) and "brackets" in raw else raw
    result = {}
    for b in ["Micro", "Low", "Mid"]:
        b_data = brackets.get(b, {}) if isinstance(brackets, dict) else {}
        if not isinstance(b_data, dict):
            b_data = {}
        cnt = int(b_data.get("count") or b_data.get("trades") or b_data.get("total") or 0)
        wr = float(b_data.get("winrate", 0.0) or 0.0)
        if 0 < wr <= 1.0:
            wr *= 100.0
        result[b] = {
            "count": cnt,
            "winrate": round(wr, 1),
            "pnl_sol": round(float(b_data.get("pnl_sol") or b_data.get("total_pnl") or 0.0), 3),
            "progress_pct": min(100, round((cnt / 30.0) * 100, 1))
        }
    return result

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard HTML introuvable</h1>", status_code=500)

@app.get("/api/state")
async def get_state():
    metrics, recent_trades = compute_metrics_and_trades()
    active_pos = format_active_positions()
    metrics["active_count"] = len(active_pos)
    return JSONResponse({
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics,
        "config": load_config(),
        "active_positions": active_pos,
        "recent_trades": recent_trades,
        "rejected_tokens": read_jsonl(REJECTS_PATH, limit=40),
        "narrative": format_narratives(),
        "tier1_wallets": format_tier1(),
        "ml_weights": format_ml_weights()
    })

@app.post("/api/config")
async def update_config(payload: Dict[str, Any] = Body(...)):
    cfg = load_config()
    for k in ["bot_paused", "min_score", "trade_size_sol", "stop_loss_pct", "take_profit_pct"]:
        if k in payload:
            cfg[k] = payload[k]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return JSONResponse({"status": "ok", "config": cfg})

@app.post("/api/panic-sell/{mint}")
async def panic_sell(mint: str):
    raw_pos = read_json(POSITIONS_PATH, {})
    pos_data = None
    if isinstance(raw_pos, dict) and mint in raw_pos:
        pos_data = raw_pos.pop(mint)
        with open(POSITIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(raw_pos, f, indent=2)
    elif isinstance(raw_pos, list):
        new_list = []
        for p in raw_pos:
            if isinstance(p, dict) and (p.get("mint") == mint or p.get("contract_address") == mint):
                pos_data = p
            else:
                new_list.append(p)
        if pos_data is not None:
            with open(POSITIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(new_list, f, indent=2)

    if not pos_data:
        return JSONResponse({"status": "error", "message": "Position introuvable"}, status_code=404)

    trades = read_json(TRADES_PATH, [])
    if not isinstance(trades, list):
        trades = []
    entry = float(pos_data.get("entry_price") or pos_data.get("buy_price") or 0.0)
    current = float(pos_data.get("current_price") or pos_data.get("last_price") or entry)
    invested = float(pos_data.get("trade_size") or pos_data.get("amount_sol") or pos_data.get("invested_sol") or 0.05)
    pnl_pct = ((current - entry) / entry * 100.0) if entry > 0 else 0.0
    pnl_sol = invested * (pnl_pct / 100.0)

    trades.append({
        "timestamp": datetime.now().isoformat(),
        "action": "SELL",
        "contract_address": mint,
        "ticker": pos_data.get("ticker") or f"PUMP_{mint[:4]}",
        "price_usd": current,
        "trade_size": invested,
        "pnl_sol": round(pnl_sol, 6),
        "pnl_pct": round(pnl_pct, 2),
        "fees_sol": 0.0005,
        "reason": "PANIC_SELL_MANUAL",
        "kols": pos_data.get("kols") or []
    })
    with open(TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)

    return JSONResponse({"status": "ok", "mint": mint, "pnl_sol": round(pnl_sol, 4)})

if __name__ == "__main__":
    print("======== Running Quant Terminal PRO on http://0.0.0.0:8080 ========")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
