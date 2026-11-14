import json, os
from collections import defaultdict

def sort_kols():
    trades_path = "logs/paper_trades.json"
    wallets_path = "data/smart_wallets.json"
    tier1_path = "data/smart_wallets_tier1.json"
    
    if not os.path.exists(trades_path) or not os.path.exists(wallets_path):
        print("Fichiers manquants pour l'analyse KOL.")
        return

    trades = json.load(open(trades_path))
    sells = [t for t in trades if t.get("action", "").upper() == "SELL"]
    
    kol_stats = defaultdict(lambda: {"calls": 0, "wins": 0, "pnl": 0.0})
    
    for s in sells:
        pnl = float(s.get("pnl_sol", 0.0) or 0.0)
        for k in s.get("kols", []):
            kol_stats[k]["calls"] += 1
            kol_stats[k]["pnl"] += pnl
            if pnl > 0:
                kol_stats[k]["wins"] += 1

    tier1 = []
    for k, stats in kol_stats.items():
        wr = (stats["wins"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
        if stats["calls"] >= 3 and wr >= 60.0:
            tier1.append({
                "address": k,
                "calls": stats["calls"],
                "winrate": round(wr, 1),
                "total_pnl_generated": round(stats["pnl"], 4)
            })
            
    tier1.sort(key=lambda x: (x["winrate"], x["total_pnl_generated"]), reverse=True)
    
    os.makedirs("data", exist_ok=True)
    json.dump({"tier1": tier1}, open(tier1_path, "w"), indent=2)
    print(f"\n✅ Tri terminé : {len(tier1)} KOLs qualifiés Tier 1 enregistrés.")

if __name__ == "__main__":
    sort_kols()
