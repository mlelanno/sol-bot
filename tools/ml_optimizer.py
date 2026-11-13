import json
import os
from datetime import datetime
from typing import List, Dict, Any


class MLOptimizer:
    """Optimizer autonome du bot de paper-trading Solana. Analyse les trades simulés pour calculer des statistiques par bracket de Market Cap et déduire les poids recommandés pour les futurs investissements."""

    def __init__(self, trades_file: str = "/home/kilpi/trading_bot/logs/paper_trades.json"):
        self.trades_file = trades_file
        self.trades: List[Dict[str, Any]] = []

    def load_trades(self) -> bool:
        if not os.path.exists(self.trades_file):
            print(f"[ML-OPT] Fichier de trades non trouvé : {self.trades_file}")
            return False
        try:
            with open(self.trades_file, "r") as f:
                data = json.load(f)
                if not isinstance(data, list) or not data:
                    print("[ML-OPT] Aucun trade à analyser.")
                    return False
                self.trades = data
                return True
        except json.JSONDecodeError as e:
            print(f"[ML-OPT] Erreur de décodage JSON : {e}")
            return False
        except Exception as e:
            print(f"[ML-OPT] Erreur inattendue lors du chargement des trades : {e}")
            return False

    def reconstruct_sessions(self) -> List[Dict[str, Any]]:
        pending_buys = {}
        sessions = []
        for trade in self.trades:
            action = trade.get("action")
            contract = trade.get("contract")
            if not contract:
                continue
            if action == "BUY":
                entry_mc = trade.get("market_cap") or trade.get("mc_usd")
                pending_buys.setdefault(contract, []).append({"timestamp": trade.get("timestamp"), "entry_mc": entry_mc})
            elif action == "SELL":
                pnl_sol = trade.get("pnl_sol")
                if pnl_sol is None:
                    continue
                if contract in pending_buys and pending_buys[contract]:
                    buy_info = pending_buys[contract].pop(0)
                    entry_mc = buy_info.get("entry_mc")
                    status = "Win" if pnl_sol > 0 else "Loss"
                    if entry_mc is None:
                        continue
                    if entry_mc < 15000:
                        bracket = "Micro"
                    elif entry_mc <= 50000:
                        bracket = "Low"
                    else:
                        bracket = "Mid"
                    sessions.append({"contract": contract, "entry_mc": entry_mc, "pnl_sol": pnl_sol, "status": status, "bracket": bracket})
        return sessions

    def compute_bracket_stats(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        brackets = ["Micro", "Low", "Mid"]
        stats = {}
        for bracket in brackets:
            filtered = [s for s in sessions if s["bracket"] == bracket]
            if not filtered:
                stats[bracket] = {"count": 0, "winrate": 0.0, "avg_pnl_sol": 0.0}
                continue
            wins = [s for s in filtered if s["status"] == "Win"]
            winrate = (len(wins) / len(filtered)) * 100.0
            avg_pnl = sum(s["pnl_sol"] for s in filtered) / len(filtered)
            stats[bracket] = {
                "count": len(filtered),
                "winrate": round(winrate, 2),
                "avg_pnl_sol": round(avg_pnl, 6),
            }
        return stats

    def determine_best_bracket(self, stats: Dict[str, Any]) -> str:
        best_bracket = "Micro"
        best_score = -float("inf")
        for bracket, data in stats.items():
            if not data["avg_pnl_sol"] and not data["winrate"]:
                continue
            score = data["winrate"] * data["avg_pnl_sol"]
            if score > best_score:
                best_score = score
                best_bracket = bracket
        return best_bracket

    def generate_recommended_action(self, best_bracket: str) -> str:
        actions = {
            "Micro": "Concentrez-vous sur les tokens à très faible capitalisation (Micro) pour des gains rapides.",
            "Low": "Ciblez les tokens à capitalisation moyenne (Low) pour un équilibre risque/rendement.",
            "Mid": "Privilégiez les tokens à forte capitalisation (Mid) pour des trades plus stables et mieux capitalisés.",
        }
        return actions.get(best_bracket, "Aucune action recommandée.")

    def run(self) -> None:
        print("[ML-OPT] Démarrage de l'optimisation...\n")
        if not self.load_trades():
            print("[ML-OPT] Pas de données à analyser. Arrêt.")
            return
        sessions = self.reconstruct_sessions()
        total_trades = len(self.trades)
        analyzed_sessions = len(sessions)
        print(f"[ML-OPT] Sessions reconstruites : {analyzed_sessions} d'un total de {total_trades} trades.")
        if analyzed_sessions == 0:
            print("[ML-OPT] Pas de sessions de trade complètes. Arrêt.")
            return
        stats = self.compute_bracket_stats(sessions)
        global_winrate = sum(1 for s in sessions if s["status"] == "Win") / analyzed_sessions * 100.0 if analyzed_sessions > 0 else 0.0
        best_bracket = self.determine_best_bracket(stats)
        recommendation = self.generate_recommended_action(best_bracket)
        output = {
            "last_optimized": datetime.now().isoformat() + "Z",
            "total_analyzed_trades": analyzed_sessions,
            "global_winrate_pct": round(global_winrate, 2),
            "best_mc_bracket": best_bracket,
            "mc_brackets_stats": stats,
            "recommended_action": recommendation,
        }
        output_dir = "/home/kilpi/trading_bot/data"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "ml_weights.json")
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"[ML-OPT] Poids sauvegardés dans {output_file}")
        print(f"[ML-OPT] Statut global des trades : {round(global_winrate, 2)}%")
        print(f"[ML-OPT] Meilleur bracket de capitalisation : {best_bracket}")
        print(f"[ML-OPT] Recommandation : {recommendation}")
        print("[ML-OPT] Optimisation terminée.\n")


if __name__ == "__main__":
    optimizer = MLOptimizer()
    optimizer.run()