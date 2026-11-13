import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config_manager import ConfigManager
from core.paper_engine import PaperTradingEngine
from core.risk_scanner import RiskScanner
from core.scoring_engine import ScoringEngine
BASE_DIR = "/home/kilpi/trading_bot"
TRADES_FILE = os.path.join(BASE_DIR, "logs/paper_trades.json")
POSITIONS_FILE = os.path.join(BASE_DIR, "data/active_positions.json")
ML_WEIGHTS_FILE = os.path.join(BASE_DIR, "data/ml_weights.json")
TIER1_FILE = os.path.join(BASE_DIR, "data/smart_wallets_tier1.json")
NARRATIVE_FILE = os.path.join(BASE_DIR, "data/narrative_signals.json")
AUDIT_FILE = os.path.join(BASE_DIR, "logs/narrative_audit.jsonl")
REJECTED_FILE = os.path.join(BASE_DIR, "logs/rejected_tokens.jsonl")
config_manager = ConfigManager()
engine = PaperTradingEngine()
risk_scanner = RiskScanner()
scoring_engine = ScoringEngine()

def load_json(path, default=None):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        return default

def fmt(x, d=4): return f"{x:.{d}f}"
def pcte(v): return f"{v*100:.2f}%"

def get_metrics():
    trades = load_json(TRADES_FILE, [])
    sells = [t for t in trades if t.get("action")=="SELL" and t.get("pnl_sol") is not None]
    pnl_vals = [t["pnl_sol"] for t in sells]
    wins = [v for v in pnl_vals if v > 0]
    losses = [v for v in pnl_vals if v < 0]
    total = len(sells)
    winrate = (len(wins)/total*100) if total else 0.0
    total_pnl = sum(pnl_vals)
    total_profit = sum(v for v in pnl_vals if v > 0)
    total_loss = abs(sum(v for v in pnl_vals if v < 0))
    pf = total_profit/total_loss if total_loss else (float("inf") if total_profit > 0 else 0.0)
    cap = 2.0; peak = 2.0; max_dd_sol = 0.0; max_dd_pct = 0.0
    for t in trades:
        if t.get("action")=="BUY" and t.get("amount_sol"): cap -= t["amount_sol"]
        elif t.get("action")=="SELL" and t.get("pnl_sol") is not None: cap += t["pnl_sol"]
        if cap > peak: peak = cap
        if cap < peak: dd = peak - cap; max_dd_sol = max(max_dd_sol, dd); max_dd_pct = max(max_dd_pct, dd/peak*100) if peak else 0
    active = load_json(POSITIONS_FILE, {})
    return {"balance": fmt(engine.sol_balance), "total_pnl_sol": fmt(total_pnl), "winrate_pct": fmt(winrate), "profit_factor": fmt(pf), "max_drawdown_sol": fmt(max_dd_sol), "max_drawdown_pct": fmt(max_dd_pct), "total_trades": len(trades), "active_positions": len(active)}

def get_active_positions():
    positions = load_json(POSITIONS_FILE, {})
    out = []
    for mint, pos in positions.items():
        entry = pos.get("entry_price_usd", 0)
        current = 0.0
        pnl_pct = ((current/entry)-1)*100 if entry else 0
        out.append({"mint": mint, "ticker": pos.get("ticker", mint[:6]), "entry_price_usd": fmt(entry), "current_price_usd": fmt(current), "pnl_percent": fmt(pnl_pct), "sol_invested": fmt(pos.get("sol_invested",0.05)), "score_entry": fmt(pos.get("score_entry",0)), "kols": pos.get("kols",[])})
    return out

def get_recent_trades():
    trades = load_json(TRADES_FILE, [])
    sells = [t for t in trades if t.get("action")=="SELL" and t.get("pnl_sol") is not None]
    out = []
    for t in sells[-30:]:
        out.append({"ticker": t.get("ticker","?"), "mint": t.get("contract","?")[:12]+"…", "duration": "—", "pnl_sol": fmt(t["pnl_sol"]), "pnl_pct": fmt(t.get("pnl_percent",0)), "reason": t.get("reason","?")})
    return out

def get_rejected_tokens():
    try:
        with open(REJECTED_FILE) as f: lines = f.read().strip().split("\\n")[-20:]
    except: lines = []
    out = []
    for l in lines:
        try: obj = json.loads(l)
        except: continue
        out.append({"mint": obj.get("mint","?"), "ticker": obj.get("ticker","?"), "name": obj.get("name","?"), "score": obj.get("score","?"), "reason": obj.get("reason","?"), "mc_bracket": obj.get("mc_bracket","?")})
    return out

def get_narrative():
    signals = load_json(NARRATIVE_FILE, [])
    now = __import__("time").time()
    active = [s for s in signals if now - s.get("timestamp",0) <= 1800]
    audit = load_json(AUDIT_FILE, [])
    last15 = audit[-15:] if isinstance(audit, list) else []
    return {"active": active, "audit": last15}

def get_tier1_wallets(): return load_json(TIER1_FILE, [])
def get_ml_weights(): mw = load_json(ML_WEIGHTS_FILE, {}); brackets = ["Micro","Low","Mid"]; out = {}; [out.__setitem__(b, {"count": stats.get("count",0), "winrate": stats.get("winrate",0.0), "progress": min(stats.get("count",0)/30,1.0)}) for b, stats in mw.get("mc_brackets_stats",{}).items()]; return out
def get_ml_weights():
    mw = load_json(ML_WEIGHTS_FILE, {}); brackets = ["Micro","Low","Mid"]; out = {}; [out.__setitem__(b, {"count": stats.get("count",0), "winrate": stats.get("winrate",0.0), "progress": min(stats.get("count",0)/30,1.0)}) for b, stats in mw.get("mc_brackets_stats",{}).items()]; return out

def render_html():
    m = get_metrics()
    pos = get_active_positions()
    recent = get_recent_trades()
    rejected = get_rejected_tokens()
    narr = get_narrative()
    tier1 = get_tier1_wallets()
    ml = get_ml_weights()
    html = "<!DOCTYPE html><html lang=\"en\" x-data=\"app\" x-init=\"init()\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Quant Terminal</title><script src=\"https://cdn.jsdelivr.net/npm/tailwindcss@3.4.0/dist/tailwind.min.js\"></script><script src=\"https://cdn.jsdelivr.net/npm/alpinejs@3.14.0/dist/cdn.min.js\"></script><style>:root { --bg:#0B0E11; --panel:#12161C; --border:#1E2329; --accent:#00FFA3; --danger:#FF3B69; --text:#E5E7EB; --muted:#6B7280; }* { box-sizing:border-box; margin:0; padding:0; }body { font-family:ui-monospace,Menlo,Monaco,Consolas,\"Courier New\",monospace; background:var(--bg); color:var(--text); min-height:100vh; }h1,h2,h3 { color:var(--text); }a { color:var(--accent); text-decoration:none; }.panel { background:var(--panel); border:1px solid var(--border); }.shadow-inner { box-shadow:inset 0 2px 4px rgba(0,0,0,.3); }.bg-glow { background:linear-gradient(180deg,rgba(0,255,163,.03),transparent); }html,body { overflow-x:hidden; overflow-y:auto; max-height:100vh; }.scroll-pane { overflow-y:auto; -ms-overflow-style:none; }.scroll-pane::-webkit-scrollbar { display:none; }.kill-switch { transition:background .2s; }.kill-switch.ACTIVE { background:var(--danger); color:white; }.kill-switch.INACTIVE { background:var(--muted); color:var(--text); }.tab { @apply text-sm font-medium; }.tab.active { @apply text-accent border-b-2 border-accent; }" + head_end + top_bar + grid_start + left_start + left_mid + left_end + central_start + central_end + right_start + right_mid + right_end + js_start + js_cont + js_end