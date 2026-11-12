import os, re, json, time, aiohttp
from aiohttp import web

BASE_DIR = "/home/kilpi/trading_bot"
TRADES_FILE = os.path.join(BASE_DIR, "logs/paper_trades.json")
POSITIONS_FILE = os.path.join(BASE_DIR, "data/active_positions.json")
LISTENER_LOG = os.path.join(BASE_DIR, "logs/helius_listener.log")
MANAGER_LOG = os.path.join(BASE_DIR, "logs/position_manager.log")
PRICE_CACHE = {}
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

def read_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def tail_lines(path, n=18):
    if not os.path.exists(path): return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
        return [ANSI_ESCAPE.sub("", l).strip() for l in lines if l.strip()]
    except Exception: return []

async def fetch_prices(session, mints):
    if not mints: return PRICE_CACHE
    url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(mints[:30])}"
    try:
        async with session.get(url, timeout=3) as resp:
            if resp.status == 200:
                data = await resp.json()
                for pair in data.get("pairs") or []:
                    base = pair.get("baseToken", {}).get("address")
                    price = float(pair.get("priceUsd") or 0)
                    if base and price > 0:
                        PRICE_CACHE[base] = {"price_usd": price, "mc_usd": float(pair.get("fdv") or 0), "ticker": pair.get("baseToken", {}).get("symbol", "")}
    except Exception: pass
    return PRICE_CACHE

async def api_data(request):
    trades = read_json(TRADES_FILE, [])
    positions_raw = read_json(POSITIONS_FILE, {})
    cache = await fetch_prices(request.app["http_session"], list(positions_raw.keys()))
    active_list, tot_unr, tot_inv = [], 0.0, 0.0
    for mint, pos in positions_raw.items():
        entry = float(pos.get("entry_price_usd") or 0)
        sol_inv = float(pos.get("sol_invested") or 0.05)
        c = cache.get(mint, {})
        curr = c.get("price_usd", entry)
        pnl_pct = ((curr - entry) / entry * 100.0) if entry > 0 else 0.0
        pnl_sol = sol_inv * (pnl_pct / 100.0)
        tot_unr += pnl_sol
        tot_inv += sol_inv
        age_min = max(0, int(time.time() - float(pos.get("entry_timestamp") or time.time())) // 60)
        active_list.append({"mint": mint, "ticker": pos.get("ticker") or c.get("ticker") or mint[:6], "entry_price": entry, "current_price": curr, "sol_invested": sol_inv, "pnl_pct": round(pnl_pct, 2), "pnl_sol": round(pnl_sol, 4), "mc_usd": c.get("mc_usd", 0), "tp1": bool(pos.get("tp1_executed", False)), "age_min": age_min})
    active_list.sort(key=lambda x: x["pnl_pct"], reverse=True)
    sells = [t for t in trades if t.get("action") == "SELL"]
    wins = [t for t in sells if float(t.get("pnl_sol") or 0) > 0]
    real_pnl = sum(float(t.get("pnl_sol") or 0) for t in sells)
    winrate = (len(wins) / len(sells) * 100.0) if sells else 0.0
    bal = trades[-1].get("remaining_sol") if trades and "remaining_sol" in trades[-1] else None
    return web.json_response({"stats": {"realized_pnl_sol": round(real_pnl, 4), "unrealized_pnl_sol": round(tot_unr, 4), "winrate": round(winrate, 1), "closed_trades": len(sells), "wins": len(wins), "active_count": len(active_list), "invested_sol": round(tot_inv, 3), "sol_balance": bal}, "active_positions": active_list, "history": list(reversed(trades[-15:])), "logs": {"listener": tail_lines(LISTENER_LOG, 18), "manager": tail_lines(MANAGER_LOG, 14)}})

HTML_PAGE = """<!DOCTYPE html>
<html lang="fr" class="dark">
<head>
  <meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SOL Smart Money Terminal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>body{background:#0b0e14;color:#e2e8f0;font-family:ui-monospace,monospace}.card{background:#131722;border:1px solid #1e293b}</style>
</head>
<body class="p-4 md:p-6 max-w-7xl mx-auto">
  <div class="flex justify-between items-center mb-6 pb-4 border-b border-slate-800">
    <div class="flex items-center gap-3"><span class="w-3 h-3 rounded-full bg-emerald-400 animate-pulse"></span><h1 class="text-xl font-bold text-white">SOL SMART MONEY <span class="text-emerald-400">TERMINAL</span></h1></div>
    <div class="text-xs text-slate-400" id="last-update">Connexion...</div>
  </div>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
    <div class="card rounded-lg p-4"><div class="text-xs text-slate-400">PNL LATENT</div><div class="text-2xl font-bold mt-1" id="kpi-unrealized">0.0000 SOL</div><div class="text-xs text-slate-500 mt-1" id="kpi-invested">0.00 SOL</div></div>
    <div class="card rounded-lg p-4"><div class="text-xs text-slate-400">PNL RÉALISÉ</div><div class="text-2xl font-bold mt-1" id="kpi-realized">0.0000 SOL</div><div class="text-xs text-slate-500 mt-1" id="kpi-balance">Paper Mode</div></div>
    <div class="card rounded-lg p-4"><div class="text-xs text-slate-400">WINRATE</div><div class="text-2xl font-bold text-sky-400 mt-1" id="kpi-winrate">0.0%</div><div class="text-xs text-slate-500 mt-1" id="kpi-closed">0 clos</div></div>
    <div class="card rounded-lg p-4"><div class="text-xs text-slate-400">ACTIVES</div><div class="text-2xl font-bold text-amber-400 mt-1" id="kpi-active">0</div><div class="text-xs text-slate-500 mt-1">Consensus 2 KOLs</div></div>
  </div>
  <div class="card rounded-lg mb-6 overflow-x-auto">
    <div class="px-4 py-3 border-b border-slate-800 flex justify-between"><h2 class="text-sm font-semibold text-white">POSITIONS ACTIVES (DEXSCREENER LIVE)</h2><span class="text-xs text-slate-400">SL -30% | TP1 +100% | TP2 +300%</span></div>
    <table class="w-full text-left text-xs"><thead class="bg-slate-900/70 text-slate-400"><tr><th class="px-4 py-3">Token</th><th class="px-4 py-3">Entrée</th><th class="px-4 py-3">Actuel</th><th class="px-4 py-3">MC</th><th class="px-4 py-3">Mise</th><th class="px-4 py-3">Statut</th><th class="px-4 py-3 text-right">PnL Live</th></tr></thead><tbody id="active-tbody" class="divide-y divide-slate-800/70"></tbody></table>
  </div>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
    <div class="card rounded-lg"><div class="px-4 py-2 border-b border-slate-800 text-xs font-semibold text-emerald-400">FLUX HELIUS KOLS</div><div id="log-listener" class="p-3 h-52 overflow-y-auto text-[11px] space-y-1"></div></div>
    <div class="card rounded-lg"><div class="px-4 py-2 border-b border-slate-800 text-xs font-semibold text-sky-400">POSITION MANAGER TP/SL</div><div id="log-manager" class="p-3 h-52 overflow-y-auto text-[11px] space-y-1"></div></div>
  </div>
  <div class="card rounded-lg overflow-x-auto">
    <div class="px-4 py-3 border-b border-slate-800"><h2 class="text-sm font-semibold text-white">DERNIÈRES OPÉRATIONS</h2></div>
    <table class="w-full text-left text-xs"><thead class="bg-slate-900/70 text-slate-400"><tr><th class="px-4 py-3">Heure</th><th class="px-4 py-3">Action</th><th class="px-4 py-3">Token</th><th class="px-4 py-3">Motif</th><th class="px-4 py-3">Prix</th><th class="px-4 py-3 text-right">Résultat</th></tr></thead><tbody id="history-tbody" class="divide-y divide-slate-800/70"></tbody></table>
  </div>
  <script>
    const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const fmt=p=>(!p||p<=0)?"$0.00":(p<0.01?"$"+Number(p).toExponential(3):"$"+Number(p).toFixed(4));
    const col=v=>v>0?"text-emerald-400":(v<0?"text-rose-400":"text-slate-300");
    async function refresh(){
      try{
        const d=await(await fetch("/api/data")).json(), s=d.stats;
        const u=document.getElementById("kpi-unrealized"); u.textContent=(s.unrealized_pnl_sol>=0?"+":"")+s.unrealized_pnl_sol.toFixed(4)+" SOL"; u.className="text-2xl font-bold mt-1 "+col(s.unrealized_pnl_sol);
        document.getElementById("kpi-invested").textContent=s.invested_sol+" SOL engagés";
        const r=document.getElementById("kpi-realized"); r.textContent=(s.realized_pnl_sol>=0?"+":"")+s.realized_pnl_sol.toFixed(4)+" SOL"; r.className="text-2xl font-bold mt-1 "+col(s.realized_pnl_sol);
        document.getElementById("kpi-balance").textContent=s.sol_balance!==null?"Solde: "+s.sol_balance+" SOL":"Paper Mode";
        document.getElementById("kpi-winrate").textContent=s.winrate+"%";
        document.getElementById("kpi-closed").textContent=s.wins+"/"+s.closed_trades+" gagnants";
        document.getElementById("kpi-active").textContent=s.active_count;
        document.getElementById("active-tbody").innerHTML=d.active_positions.length?d.active_positions.map(p=>`<tr class="hover:bg-slate-800/40"><td class="px-4 py-3 font-bold text-white"><a href="https://trade.padre.gg/trade/solana/${esc(p.mint)}" target="_blank" class="hover:text-emerald-400 underline">${esc(p.ticker)}</a> <span class="text-[10px] text-slate-500">${p.age_min}m</span></td><td class="px-4 py-3">${fmt(p.entry_price)}</td><td class="px-4 py-3 text-white">${fmt(p.current_price)}</td><td class="px-4 py-3 text-slate-400">$${Math.round(p.mc_usd).toLocaleString()}</td><td class="px-4 py-3">${p.sol_invested} SOL</td><td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-[10px] ${p.tp1?"bg-emerald-500/20 text-emerald-300":"bg-slate-700"}">${p.tp1?"TP1 PRIS":"EN COURS"}</span></td><td class="px-4 py-3 text-right font-bold ${col(p.pnl_pct)}">${p.pnl_pct>=0?"+":""}${p.pnl_pct.toFixed(2)}% (${p.pnl_sol>=0?"+":""}${p.pnl_sol.toFixed(4)} SOL)</td></tr>`).join(""):'<tr><td colspan="7" class="px-4 py-6 text-center text-slate-500">Aucune position active</td></tr>';
        document.getElementById("history-tbody").innerHTML=d.history.map(t=>{const b=t.action==="BUY",ts=(t.timestamp||"").split("T")[1]?.slice(0,8)||"--:--:--",pr=b?t.entry_price_usd:t.exit_price_usd,rt=b?`-${t.amount_sol||0.05} SOL`:`${t.pnl_percent>=0?"+":""}${t.pnl_percent}% (${t.pnl_sol>=0?"+":""}${t.pnl_sol} SOL)`;return`<tr class="hover:bg-slate-800/40"><td class="px-4 py-2 text-slate-400">${esc(ts)}</td><td class="px-4 py-2 font-bold ${b?"text-sky-400":"text-amber-400"}">${esc(t.action)}</td><td class="px-4 py-2 text-white font-semibold">${esc(t.ticker||"")}</td><td class="px-4 py-2 text-slate-400">${esc(t.reason||"CONSENSUS")}</td><td class="px-4 py-2">${fmt(pr)}</td><td class="px-4 py-2 text-right font-bold ${b?"text-slate-400":col(t.pnl_sol)}">${rt}</td></tr>`}).join("");
        document.getElementById("log-listener").innerHTML=d.logs.listener.map(l=>`<div>${esc(l)}</div>`).join("");
        document.getElementById("log-manager").innerHTML=d.logs.manager.map(l=>`<div>${esc(l)}</div>`).join("");
        document.getElementById("last-update").textContent="MAJ : "+new Date().toLocaleTimeString();
      }catch(e){document.getElementById("last-update").textContent="Erreur MAJ";}
    }
    refresh(); setInterval(refresh, 3000);
  </script>
</body></html>"""

async def index(request): return web.Response(text=HTML_PAGE, content_type="text/html")
async def on_startup(app): app["http_session"] = aiohttp.ClientSession()
async def on_cleanup(app): await app["http_session"].close()

app = web.Application()
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
app.router.add_get("/", index)
app.router.add_get("/api/data", api_data)

if __name__ == "__main__":
    print("🌐 Web Dashboard actif sur http://0.0.0.0:8080")
    web.run_app(app, host="0.0.0.0", port=8080, print=None)
