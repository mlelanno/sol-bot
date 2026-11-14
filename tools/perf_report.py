import json, os

def generate_report():
    paths = ["logs/paper_trades.json", "logs/paper_trades_v1_backup.json"]
    trades = []
    for p in paths:
        if os.path.exists(p):
            try: trades.extend(json.load(open(p)))
            except: pass

    buys = {t.get("contract_address", t.get("mint")): t for t in trades if t.get("action", "").upper() == "BUY"}
    sells = [t for t in trades if t.get("action", "").upper() == "SELL"]

    wins, losses = 0, 0
    gross_profit, gross_loss = 0.0, 0.0
    equity, peak, max_dd = 2.0, 2.0, 0.0

    for s in sells:
        pnl = float(s.get("pnl_sol", s.get("pnl", 0.0)) or 0.0)
        fees = float(s.get("fees_sol", 0.0005) or 0.0005)
        net = pnl - fees
        
        if net > 0:
            wins += 1
            gross_profit += net
        else:
            losses += 1
            gross_loss += abs(net)
            
        equity += net
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100 if peak > 0 else 0)

    total = wins + losses
    winrate = (wins / total * 100) if total > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    print("\n" + "="*40)
    print("📊 RAPPORT DE PERFORMANCE BASELINE")
    print("="*40)
    print(f"Trades clôturés : {total}")
    print(f"Winrate         : {winrate:.1f}%")
    print(f"Profit Factor   : {pf:.2f}")
    print(f"Max Drawdown    : -{max_dd:.2f}%")
    print(f"Moyenne Gain    : +{(gross_profit/wins if wins else 0):.4f} SOL")
    print(f"Moyenne Perte   : -{(gross_loss/losses if losses else 0):.4f} SOL")
    print("="*40 + "\n")

if __name__ == "__main__":
    generate_report()
