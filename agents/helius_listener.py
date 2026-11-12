import os, json, time, asyncio, aiohttp
from aiohttp import web
from collections import defaultdict

BASE_DIR = "/home/kilpi/trading_bot"
WALLETS_FILE = os.path.join(BASE_DIR, "data/smart_wallets.json")
AUDIT_FILE = os.path.join(BASE_DIR, "data/audit_narratives.json")

WALLET_MAP = {}
if os.path.exists(WALLETS_FILE):
    with open(WALLETS_FILE, "r") as f:
        for w in json.load(f):
            if w.get("address"): WALLET_MAP[w["address"].strip()] = w.get("name", "KOL")

clusters = defaultdict(dict)

from core.paper_engine import PaperTradingEngine
from core.risk_scanner import RiskScanner

paper_engine = PaperTradingEngine()
risk_scanner = RiskScanner()
SOL_PRICE = 170.0


def save_audit(mint, data):
    audits = {}
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r") as f: audits = json.load(f)
        except: pass
    if mint not in audits:
        audits[mint] = data
        with open(AUDIT_FILE, "w") as f: json.dump(audits, f, indent=2)

async def process_event(session, event):
    # Extraction propre des acteurs
    cands = [event.get("feePayer")]
    for t in event.get("tokenTransfers") or []: cands.extend([t.get("fromUserAccount"), t.get("toUserAccount")])
    for n in event.get("nativeTransfers") or []: cands.extend([n.get("fromUserAccount"), n.get("toUserAccount")])
    kol = next((c for c in cands if c and c in WALLET_MAP), None)
    if not kol: return

    # Detection Swap (PumpSwap / Raydium)
    sol_spent, mint = 0.0, None
    tokens_received = 0
    for t in event.get("tokenTransfers") or []:
        if t.get("toUserAccount") == kol and t.get("mint") != "So11111111111111111111111111111111111111112":
            mint = t.get("mint")
            tokens_received = float(t.get("tokenAmount") or 0)
        elif t.get("fromUserAccount") == kol and t.get("mint") == "So11111111111111111111111111111111111111112":
            sol_spent += float(t.get("tokenAmount") or 0)
    
    if not mint or tokens_received < 0.05: return

    now = time.time()
    clusters[mint][kol] = {"time": now, "sol": sol_spent, "name": WALLET_MAP[kol]}
    
    # Clean up > 60s
    clusters[mint] = {k: v for k, v in clusters[mint].items() if now - v["time"] <= 60}
    
    # Consensus = 2 KOLs
    if len(clusters[mint]) >= 2:
        # Calcul du prix On-Chain
        kol_price_sol = sol_spent / tokens_received if tokens_received > 0 else 0
        kol_price_usd = kol_price_sol * SOL_PRICE
        mc_usd = kol_price_usd * 1_000_000_000

        # Filtre anti-rug via RiskScanner
        is_safe, reasons = await risk_scanner.evaluate_token(mint, mc_usd=mc_usd)
        if not is_safe:
            print(f"[RISQUE] Token rejeté : {reasons}")
            return

        success, trade_record = await paper_engine.execute_buy(
            contract_address=mint,
            ticker=f"PUMP_{mint[:4]}",
            price_usd=kol_price_usd,
            mc_usd=mc_usd,
            vol_usd=sol_spent * SOL_PRICE
        )
        if success:
            print(f"ACHAT : {trade_record}")
            audit_data = {
                "mint": mint,
                "ticker": trade_record.get("ticker", mint[:6]),
                "discovered_at": now,
                "kol_price_sol": kol_price_sol,
                "kol_price_usd": kol_price_usd,
                "mc_usd": mc_usd,
                "kols": [{"wallet": k, "name": v["name"], "sol_spent": v["sol"]} for k, v in clusters[mint].items()]
            }
            save_audit(mint, audit_data)
            print(f"🚨 NARRATIVE DÉTECTÉE : {trade_record.get('ticker', mint[:6])} | MC: ${mc_usd:,.0f}")

async def handle_webhook(request):
    try:
        raw = await request.read()
        if raw:
            events = json.loads(raw.decode("utf-8"))
            if not isinstance(events, list): events = [events]
            for ev in events: await process_event(request.app["session"], ev)
    except: pass
    return web.Response(text="OK")

async def init_app():
    app = web.Application()
    app["session"] = aiohttp.ClientSession()
    app.router.add_post("/webhook", handle_webhook)
    return app

if __name__ == "__main__":
    web.run_app(init_app(), host="0.0.0.0", port=5000)
