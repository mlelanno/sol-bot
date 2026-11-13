#!/usr/bin/env python3
"""
perf_report.py — Outil de reporting statistique de baseline.

Analyse logs/paper_trades.json et génère un rapport complet :
- Nombre total de trades clôturés (paires BUY/SELL)
- Winrate global (%)
- Gain moyen / Perte moyenne (SOL)
- Profit Factor (Somme gains / |Somme pertes|)
- Max Drawdown (SOL et %)
- Répartition des performances par tranche de Market Cap
"""

import json
import os
from collections import defaultdict
from datetime import datetime

BASE_DIR = "/home/kilpi/trading_bot"
TRADES_FILE = os.path.join(BASE_DIR, "logs", "paper_trades.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "perf_baseline.json")

BRACKET_BOUNDS = [
    ("Micro", 0, 15_000),
    ("Low", 15_000, 50_000),
    ("Mid", 50_000, float("inf")),
]


def load_trades(path):
    if not os.path.exists(path):
        print(f"Erreur : {path} introuvable.")
        return []

    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        print(f"Erreur : le fichier n'est pas un tableau JSON.")
        return []
    except json.JSONDecodeError as e:
        print(f"Erreur de décodage JSON : {e}")
        return []
    except Exception as e:
        print(f"Erreur lors du chargement : {e}")
        return []


def classify_bracket(mc_usd):
    for name, lower, upper in BRACKET_BOUNDS:
        if lower <= mc_usd < upper:
            return name
    return "Mid"


def compute_metrics(trades):
    sell_trades = [t for t in trades if t.get("action") == "SELL" and t.get("pnl_sol") is not None]

    total_trades = len(sell_trades)
    if total_trades == 0:
        print("Aucun trade clôturé trouvé.")
        return {}

    pnl_values = [t["pnl_sol"] for t in sell_trades]
    total_profit = sum(pnl for pnl in pnl_values if pnl > 0)
    total_loss = sum(abs(pnl) for pnl in pnl_values if pnl < 0)

    wins = [p for p in pnl_values if p > 0]
    losses = [p for p in pnl_values if p < 0]
    winrate = len(wins) / total_trades * 100.0 if total_trades > 0 else 0.0

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    profit_factor = total_profit / total_loss if total_loss > 0 else (float("inf") if total_profit > 0 else 0.0)

    capital_history = []
    current_capital = 2.0
    for t in trades:
        if t.get("action") == "BUY" and t.get("amount_sol"):
            current_capital -= t["amount_sol"]
        elif t.get("action") == "SELL" and t.get("pnl_sol") is not None:
            current_capital += t["pnl_sol"]
        if current_capital > 0:
            capital_history.append(current_capital)

    max_drawdown_sol = 0.0
    max_drawdown_pct = 0.0
    if capital_history:
        peak = max(capital_history)
        trough = min(capital_history)
        max_drawdown_sol = peak - trough
        max_drawdown_pct = (max_drawdown_sol / peak * 100.0) if peak > 0 else 0.0

    bracket_stats = defaultdict(lambda: {"count": 0, "trades": [], "profit": 0.0, "loss": 0.0})
    for t in sell_trades:
        mc = t.get("market_cap") or t.get("mc_usd") or 0
        bracket = classify_bracket(mc)
        bracket_stats[bracket]["count"] += 1
        bracket_stats[bracket]["trades"].append(t["pnl_sol"])
        if t["pnl_sol"] > 0:
            bracket_stats[bracket]["profit"] += t["pnl_sol"]
        else:
            bracket_stats[bracket]["loss"] += abs(t["pnl_sol"])

    bracket_summary = {}
    for bracket, data in sorted(bracket_stats.items()):
        count = data["count"]
        bracket_summary[bracket] = {
            "trade_count": count,
            "avg_pnl_sol": round(sum(data["trades"]) / count, 6) if count else 0.0,
            "total_profit": round(data["profit"], 6),
            "total_loss": round(data["loss"], 6),
        }

    metrics = {
        "total_trades": total_trades,
        "winrate_pct": round(winrate, 2),
        "avg_win_sol": round(avg_win, 6),
        "avg_loss_sol": round(avg_loss, 6),
        "profit_factor": round(profit_factor, 4),
        "max_drawdown_sol": round(max_drawdown_sol, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "total_profit_sol": round(total_profit, 6),
        "total_loss_sol": round(total_loss, 6),
    }

    return metrics


def print_report(metrics):
    print("=" * 64)
    print("  📊 BASELINE DE PERFORMANCE — PAPER TRADING ENGINE")
    print("=" * 64)
    print(f"  ⏱️  Généré le : {metrics.get('generated_at', 'N/A')}")
    print("-" * 64)
    print(f"  📦 Total trades clôturés      : {metrics['total_trades']}")
    print(f"  🎯 Winrate global              : {metrics['winrate_pct']:.2f}%")
    print(f"  💰 Gagnants moyens (SOL)       : +{metrics['avg_win_sol']:.4f}")
    print(f"  💀 Perdants moyens (SOL)       : {metrics['avg_loss_sol']:.4f}")
    print(f"  ⚖️  Profit Factor              : {metrics['profit_factor']:.4f}")
    print(f"  📉 Max Drawdown (SOL)          : -{metrics['max_drawdown_sol']:.4f}")
    print(f"  📉 Max Drawdown (%)            : -{metrics['max_drawdown_pct']:.2f}%")
    print("-" * 64)
    print(f"  📊 Performance par tranche MC :")
    for bracket, data in metrics.get("bracket_performance", {}).items():
        print(
            f"     • {bracket:<6}: {data['trade_count']:>3} trades | "
            f"PnL moyen: {data['avg_pnl_sol']:+.4f} SOL | "
            f"Gains: ${data['total_profit']:.2f} | "
            f"Pertes: ${data['total_loss']:.2f}"
        )
    print("=" * 64)

    return metrics


def save_baseline(metrics, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"💾 Baseline sauvegardé : {path}")
    return metrics


if __name__ == "__main__":
    trades = load_trades(TRADES_FILE)
    if not trades:
        print("⚠️  Aucun trade à analyser.")
        exit(1)

    metrics = compute_metrics(trades)
    if not metrics:
        exit(1)

    print_report(metrics)
    save_baseline(metrics, OUTPUT_FILE)