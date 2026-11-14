import os, sys, json, asyncio, aiohttp
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

async def main():
    print("="*55)
    print("🔍 AUDIT COMPLET DE LA STACK TRADING BOT V2")
    print("="*55)

    # 1. Variables d'environnement
    helius_key = os.getenv("HELIUS_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    tg_id = os.getenv("TG_API_ID", "")
    print(f"[ENV] HELIUS_API_KEY : {'✅ OK ('+helius_key[:6]+'...)' if helius_key else '❌ MANQUANTE'}")
    print(f"[ENV] GEMINI_API_KEY : {'✅ OK ('+gemini_key[:6]+'...)' if gemini_key else '❌ MANQUANTE'}")
    print(f"[ENV] TG_API_ID      : {'✅ OK' if tg_id else '❌ MANQUANTE'}")

    timeout = aiohttp.ClientTimeout(total=5.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 2. Test Helius DAS getAsset (Vrai Ticker)
        rpc_url = os.getenv("HELIUS_RPC_URL") or f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" # BONK
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": test_mint}}
            async with session.post(rpc_url, json=payload) as r:
                d = await r.json()
                sym = (((d.get("result") or {}).get("content") or {}).get("metadata") or {}).get("symbol")
                print(f"[RPC] Helius DAS getAsset       : {'✅ OK (Ticker=' + str(sym) + ')' if sym else '❌ ÉCHEC: ' + str(d)[:80]}")
        except Exception as e:
            print(f"[RPC] Helius DAS getAsset       : ❌ ERREUR ({e})")

        # 3. Test Helius getTokenLargestAccounts (Top 10 Holders réel)
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [test_mint]}
            async with session.post(rpc_url, json=payload) as r:
                d = await r.json()
                vals = (d.get("result") or {}).get("value") or []
                print(f"[RPC] Helius Top Holders Check  : {'✅ OK (' + str(len(vals)) + ' comptes retournés)' if vals else '❌ ÉCHEC'}")
        except Exception as e:
            print(f"[RPC] Helius Top Holders Check  : ❌ ERREUR ({e})")

        # 4. Test Gemini 2.5 Flash JSON
        try:
            g_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            g_payload = {
                "contents": [{"parts": [{"text": 'Réponds uniquement en JSON: {"narrative_strength": 25, "keywords": ["bonk"], "external_catalyst": true, "shill_pattern_detected": false}'}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            async with session.post(g_url, json=g_payload) as r:
                gd = await r.json()
                txt = gd["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(txt)
                print(f"[LLM] Gemini 2.5 Flash API      : ✅ OK (strength={parsed.get('narrative_strength')})")
        except Exception as e:
            print(f"[LLM] Gemini 2.5 Flash API      : ❌ ERREUR ({e})")

        # 5. Test DexScreener API
        try:
            async with session.get(f"https://api.dexscreener.com/latest/dex/tokens/{test_mint}") as r:
                dd = await r.json()
                pairs = dd.get("pairs") or []
                print(f"[DEX] DexScreener Price/Liq API : {'✅ OK (Prix=$' + str(pairs[0].get('priceUsd')) + ')' if pairs else '❌ ÉCHEC'}")
        except Exception as e:
            print(f"[DEX] DexScreener Price/Liq API : ❌ ERREUR ({e})")

    # 6. Audit des fichiers de données et du code
    files_to_check = [
        "data/bot_config.json",
        "data/active_positions.json",
        "data/smart_wallets.json",
        "data/smart_wallets_tier1.json",
        "data/narrative_signals.json",
        "data/tg_buffer.json",
        "data/ml_weights.json",
        "logs/paper_trades.json",
        "logs/rejected_tokens.jsonl",
        "logs/narrative_audit.jsonl"
    ]
    print("-" * 55)
    for rel in files_to_check:
        p = os.path.join(BASE_DIR, rel)
        exists = os.path.exists(p)
        sz = os.path.getsize(p) if exists else 0
        print(f"[FILE] {rel:<30} : {'✅ ' + str(sz) + ' octets' if exists else '⚠️ ABSENT (0 octet)'}")

    print("-" * 55)
    # 7. Vérification de ce que web_dashboard.py attend
    dash_path = os.path.join(BASE_DIR, "tools", "web_dashboard.py")
    if os.path.exists(dash_path):
        dc = open(dash_path, encoding="utf-8").read()
        for key in ["active_positions.json", "paper_trades.json", "rejected_tokens.jsonl", "narrative_audit.jsonl", "narrative_signals.json", "ml_weights.json"]:
            print(f"[DASH] Référence {key:<22} : {'✅ OUI' if key in dc else '❌ NON'}")

if __name__ == "__main__":
    asyncio.run(main())
