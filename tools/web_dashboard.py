import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import json
import os
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import json_response

from core.paper_engine import PaperTradingEngine

BASE_DIR = "/home/kilpi/trading_bot"
TRADES_FILE = os.path.join(BASE_DIR, "logs/paper_trades.json")
POSITIONS_FILE = os.path.join(BASE_DIR, "data/active_positions.json")
ML_WEIGHTS_FILE = os.path.join(BASE_DIR, "data/ml_weights.json")
BOT_PAUSED_FILE = os.path.join(BASE_DIR, "data/bot_paused.lock")
STATIC_DIR = os.path.join(BASE_DIR, "tools", "static")

engine = PaperTradingEngine()
bot_paused = False


def read_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return default


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def compute_stats():
    trades = read_json_file(TRADES_FILE, [])
    positions = read_json_file(POSITIONS_FILE, {})
    ml_weights = read_json_file(ML_WEIGHTS_FILE, {})

    if not isinstance(trades, list):
        trades = []

    balance = engine.sol_balance

    sell_trades = [t for t in trades if t.get("action") == "SELL" and t.get("pnl_sol") is not None]
    total_pnl = sum(t.get("pnl_sol", 0) for t in sell_trades)
    wins = [t for t in sell_trades if t.get("pnl_sol", 0) > 0]
    winrate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0.0

    history = list(reversed(trades[-20:]))

    return {
        "balance": round(balance, 4),
        "total_pnl_sol": round(total_pnl, 6),
        "winrate_pct": round(winrate, 2),
        "total_trades": len(trades),
        "completed_trades": len(sell_trades),
        "ml": ml_weights,
        "history": history,
        "paused": bot_paused,
    }


async def api_stats(request: Request):
    return json_response(compute_stats())


async def api_positions(request: Request):
    positions = read_json_file(POSITIONS_FILE, {})
    active_list = []
    for mint, pos in positions.items():
        active_list.append({
            "mint": mint,
            "ticker": pos.get("ticker", mint[:6]),
            "entry_price_usd": pos.get("entry_price_usd", 0),
            "tokens_held": pos.get("tokens_held", 0),
            "sol_invested": pos.get("sol_invested", 0.05),
            "entry_timestamp": pos.get("entry_timestamp", 0),
            "tp1_executed": pos.get("tp1_executed", False),
        })
    return json_response({"positions": active_list})


async def api_force_sell(request: Request):
    global engine
    try:
        body = await request.json()
    except Exception:
        return json_response({"success": False, "error": "Invalid JSON body"}, status=400)

    mint = body.get("mint")
    ratio = body.get("ratio", 1.0)
    price_usd = body.get("price_usd", 0.0)

    if not mint:
        return json_response({"success": False, "error": "Missing mint"}, status=400)

    positions = read_json_file(POSITIONS_FILE, {})
    if mint not in positions:
        return json_response({"success": False, "error": "Position not found"}, status=404)

    position = positions[mint]
    entry_price = position.get("entry_price_usd", 0)
    if price_usd <= 0:
        price_usd = entry_price

    success, message, details = await engine.execute_sell(
        contract_address=mint,
        ratio_to_sell=float(ratio),
        current_price_usd=float(price_usd),
        reason="FORCE_SELL_DASHBOARD",
    )
    if success:
        return json_response({"success": True, "message": message, "details": details})
    else:
        return json_response({"success": False, "error": message}, status=400)


async def api_toggle_bot(request: Request):
    global bot_paused
    bot_paused = not bot_paused
    from datetime import datetime
    if bot_paused:
        write_json_file(BOT_PAUSED_FILE, {"paused": True, "timestamp": datetime.now().isoformat()})
    else:
        if os.path.exists(BOT_PAUSED_FILE):
            os.remove(BOT_PAUSED_FILE)
    return json_response({"success": True, "paused": bot_paused})


async def index(request: Request):
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return web.FileResponse(index_path)
    return web.Response(text="<h1>Control Panel</h1><p>Frontend not found at tools/static/index.html</p>", content_type="text/html")


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/api/stats", api_stats)
app.router.add_get("/api/positions", api_positions)
app.router.add_post("/api/action/force_sell", api_force_sell)
app.router.add_post("/api/action/toggle_bot", api_toggle_bot)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
