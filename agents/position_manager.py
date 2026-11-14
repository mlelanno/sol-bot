import json, os, time, asyncio, aiohttp
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITIONS_FILE = os.path.join(BASE_DIR, "data", "active_positions.json")
TRADES_FILE = os.path.join(BASE_DIR, "logs", "paper_trades.json")
CONFIG_FILE = os.path.join(BASE_DIR, "data", "bot_config.json")
ML_FILE = os.path.join(BASE_DIR, "data", "ml_weights.json")

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def atomic_save(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def update_ml_calibration(mc_usd: float, net_pnl_sol: float):
    ml = load_json(ML_FILE, {})
    b = "Micro" if mc_usd < 100_000 else ("Low" if mc_usd < 500_000 else "Mid")
    entry = ml.get(b, {"wins": 0, "trades": 0, "count": 0, "winrate": 0.0})
    cnt = int(entry.get("count", entry.get("trades", 0))) + 1
    wins = int(entry.get("wins", 0)) + (1 if net_pnl_sol > 0 else 0)
    wr = round((wins / cnt) * 100.0, 1) if cnt > 0 else 0.0
    status = "CALIBRATED" if cnt >= 30 else f"OBSERVATION ({cnt}/30)"
    ml[b] = {"wins": wins, "trades": cnt, "count": cnt, "winrate": wr, "status": status}
    atomic_save(ML_FILE, ml)

async def fetch_dex_data(mints):
    if not mints:
        return {}
    url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(mints[:30])}"
    out = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pair in data.get("pairs") or []:
                        mint = (pair.get("baseToken") or {}).get("address")
                        price = float(pair.get("priceUsd") or 0.0)
                        liq = float((pair.get("liquidity") or {}).get("usd") or 10000.0)
                        if mint and price > 0 and (mint not in out or liq > out[mint]["liq"]):
                            out[mint] = {"price": price, "liq": liq}
    except Exception as e:
        print(f"[DEX WARN] {e}")
    return out

async def manage_positions():
    print("🛡️ Position Manager V2 actif (TP/SL/Trailing/TTL + Calibration ML 30 trades)...")
    while True:
        try:
            cfg = load_json(CONFIG_FILE, {"bot_paused": False, "stop_loss_pct": -25.0, "take_profit_pct": 60.0})
            tp_pct = float(cfg.get("take_profit_pct", 60.0))
            sl_pct = float(cfg.get("stop_loss_pct", -25.0))

            positions = load_json(POSITIONS_FILE, {})
            if isinstance(positions, list):
                positions = {p.get("mint") or p.get("contract_address"): p for p in positions if isinstance(p, dict)}

            if not positions:
                await asyncio.sleep(5)
                continue

            dex_info = await fetch_dex_data(list(positions.keys()))
            trades = load_json(TRADES_FILE, [])
            changed = False
            now = time.time()

            for mint, pos in list(positions.items()):
                info = dex_info.get(mint)
                opened_at = float(pos.get("opened_at") or now)
                age_sec = now - opened_at

                # Protection Time-Stop (45 min max ou 10 min sans indexation DexScreener)
                if not info:
                    if age_sec > 600:
                        del positions[mint]
                        changed = True
                    continue

                live_price = info["price"]
                liq_usd = info["liq"]
                entry_price = float(pos.get("entry_price") or pos.get("buy_price") or 0.0)
                if entry_price <= 0:
                    continue

                raw_pnl_pct = ((live_price - entry_price) / entry_price) * 100.0
                peak_pnl = max(float(pos.get("peak_pnl_pct", 0.0)), raw_pnl_pct)
                pos["current_price"] = live_price
                pos["pnl_pct"] = round(raw_pnl_pct, 2)
                pos["peak_pnl_pct"] = round(peak_pnl, 2)
                changed = True

                exit_reason = None
                is_emergency = False
                if raw_pnl_pct >= tp_pct:
                    exit_reason = f"TAKE_PROFIT (+{raw_pnl_pct:.1f}%)"
                elif raw_pnl_pct <= sl_pct:
                    exit_reason = f"STOP_LOSS ({raw_pnl_pct:.1f}%)"
                    is_emergency = True
                elif peak_pnl >= 40.0 and raw_pnl_pct <= 12.0:
                    exit_reason = f"TRAILING_STOP (+{raw_pnl_pct:.1f}% après pic +{peak_pnl:.0f}%)"
                elif age_sec >= 2700 and abs(raw_pnl_pct) < 15.0:
                    exit_reason = f"TIME_STOP_45M ({raw_pnl_pct:+.1f}%)"

                if exit_reason:
                    invested = float(pos.get("invested_sol") or pos.get("trade_size") or 0.1)
                    # Slippage de sortie réaliste basé sur l'urgence et la liquidité
                    sell_slip = (0.12 if is_emergency else 0.04) + min(0.15, (invested * 180.0) / max(1000.0, liq_usd))
                    jito_tip = 0.0025 if is_emergency else 0.0015
                    exec_exit_price = live_price * (1.0 - sell_slip)
                    net_pnl_pct = ((exec_exit_price - entry_price) / entry_price) * 100.0
                    net_pnl_sol = (invested * (net_pnl_pct / 100.0)) - jito_tip

                    print(f"⚡ [EXIT] {pos.get('ticker', mint[:6])} | {exit_reason} | Net: {net_pnl_sol:+.4f} SOL ({net_pnl_pct:+.1f}%)")
                    trades.append({
                        "timestamp": datetime.now().isoformat(),
                        "action": "SELL",
                        "contract_address": mint,
                        "ticker": pos.get("ticker", mint[:6]),
                        "price_usd": exec_exit_price,
                        "trade_size": invested,
                        "pnl_sol": round(net_pnl_sol, 6),
                        "pnl_pct": round(net_pnl_pct, 2),
                        "fees_sol": jito_tip,
                        "reason": exit_reason,
                        "kols": pos.get("kols", [])
                    })
                    update_ml_calibration(float(pos.get("mc_usd") or 50000.0), net_pnl_sol)
                    del positions[mint]

            if changed:
                atomic_save(POSITIONS_FILE, positions)
                atomic_save(TRADES_FILE, trades)
        except Exception as e:
            print(f"[PM ERROR] {e}")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(manage_positions())
