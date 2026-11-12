import os, json, aiohttp
from aiohttp import web

BASE_DIR = "/home/kilpi/trading_bot"
AUDIT_FILE = os.path.join(BASE_DIR, "data/audit_narratives.json")

def read_audit():
    if not os.path.exists(AUDIT_FILE): return {}
    try:
        with open(AUDIT_FILE, "r") as f: return json.load(f)
    except: return {}

async def api_data(request):
    audits = read_audit()
    # Refresh live prices for UI
    session = request.app["session"]
    mints = list(audits.keys())[:30]
    live_prices = {}
    if mints:
        try:
            async with session.get(f"https://api.dexscreener.com/latest/dex/tokens/{','.join(mints)}") as r:
                if r.status == 200:
                    d = await r.json()
                    for p in (d.get("pairs") or []):
                        b = p.get("baseToken", {}).get("address")
                        if b: live_prices[b] = p
        except: pass

    results = []
    for mint, data in audits.items():
        lp = live_prices.get(mint, {})
        curr_price = float(lp.get("priceUsd") or data.get("dex_price") or 0)
        curr_mc = float(lp.get("fdv") or data.get("dex_mc") or 0)
        
        results.append({
            "mint": mint,
            "ticker": data.get("ticker", "UNKNOWN"),
            "time": data.get("discovered_at"),
            "kols": data.get("kols", []),
            "entry_price": data.get("dex_price", 0),
            "current_price": curr_price,
            "mc": curr_mc,
            "is_indexing": curr_price == 0
        })
    results.sort(key=lambda x: x["time"], reverse=True)
    return web.json_response({"narratives": results})

HTML_PAGE = """<!DOCTYPE html>
<html lang="fr" class="dark">
<head>
  <meta charset="UTF-8"><title>SOL Audit Terminal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>body{background:#0b0e14;color:#e2e8f0;font-family:ui-monospace,monospace}.card{background:#131722;border:1px solid #1e293b}</style>
</head>
<body class="p-6 max-w-7xl mx-auto">
  <h1 class="text-2xl font-bold text-white mb-6">👁️ AUDIT <span class="text-sky-400">SMART MONEY</span></h1>
  
  <div class="card rounded-lg overflow-x-auto">
    <table class="w-full text-left text-sm"><thead class="bg-slate-900 text-slate-400">
      <tr><th class="px-4 py-3">Token (Clic = Padre)</th><th class="px-4 py-3">Market Cap</th><th class="px-4 py-3">Prix</th><th class="px-4 py-3">Acheteurs (KOLs) -> Solscan</th></tr>
    </thead><tbody id="tbody" class="divide-y divide-slate-800"></tbody></table>
  </div>

  <script>
    async function refresh() {
      const res = await fetch("/api/data");
      const d = await res.json();
      document.getElementById("tbody").innerHTML = d.narratives.map(n => `
        <tr class="hover:bg-slate-800/50">
          <td class="px-4 py-4">
            <a href="https://trade.padre.gg/trade/solana/${n.mint}" target="_blank" class="font-bold text-emerald-400 hover:underline">${n.ticker}</a><br>
            <span class="text-[10px] text-slate-500">${n.mint.slice(0,8)}...</span>
          </td>
          <td class="px-4 py-4 text-slate-300">
            ${n.is_indexing ? '<span class="text-amber-400 text-xs animate-pulse">Indexation DexScreener...</span>' : '$' + n.mc.toLocaleString()}
          </td>
          <td class="px-4 py-4 text-slate-300">${n.is_indexing ? '-' : '$' + n.current_price.toFixed(6)}</td>
          <td class="px-4 py-4 text-xs space-y-1">
            ${n.kols.map(k => `
              <div class="flex items-center gap-2">
                <a href="https://solscan.io/account/${k.wallet}" target="_blank" class="text-sky-400 hover:underline">🔍 ${k.name}</a>
                <span class="text-slate-500">(${k.sol_spent.toFixed(2)} SOL)</span>
              </div>
            `).join("")}
          </td>
        </tr>
      `).join("");
    }
    refresh(); setInterval(refresh, 5000);
  </script>
</body></html>"""

async def index(request): return web.Response(text=HTML_PAGE, content_type="text/html")
async def init_app():
    app = web.Application()
    app["session"] = aiohttp.ClientSession()
    app.router.add_get("/", index)
    app.router.add_get("/api/data", api_data)
    return app

if __name__ == "__main__": web.run_app(init_app(), host="0.0.0.0", port=8080)
