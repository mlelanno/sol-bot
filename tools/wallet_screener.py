import json
import os
from collections import defaultdict

AUDIT_FILE = "/home/kilpi/trading_bot/data/audit_narratives.json"
TRADES_FILE = "/home/kilpi/trading_bot/logs/paper_trades.json"
SMART_WALLETS_FILE = "/home/kilpi/trading_bot/data/smart_wallets.json"
TIER1_FILE = "/home/kilpi/trading_bot/data/smart_wallets_tier1.json"

# NOTE: Les données réelles contiennent ~12 SELLs avec PnL (PYTH, SellMint tests, TEST_*)
# Avec min_calls = 1, on peut classer les wallets déjà impliqués dans les audtis
MIN_CALLS = 1
TOP_N = 30


class WalletScreener:
    def __init__(self):
        self.audit_file = AUDIT_FILE
        self.trades_file = TRADES_FILE
        self.smart_wallets_file = SMART_WALLETS_FILE
        self.tier1_file = TIER1_FILE

    def _load_json(self, path, default):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def run(self):
        audits = self._load_json(self.audit_file, {})
        trades = self._load_json(self.trades_file, [])
        smart_wallets = self._load_json(self.smart_wallets_file, [])

        # Build wallet -> name lookup from smart_wallets.json
        wallet_names = {}
        for w in smart_wallets:
            addr = w.get("address", "").strip()
            if addr:
                wallet_names[addr] = w.get("name", "Unknown")

        # Build mint -> kols mapping from BUY trades (primary source - KOL attribution)
        mint_to_kols = {}
        for trade in trades:
            if trade.get("action") == "BUY" and "contract" in trade:
                kols = trade.get("kols") or []
                if kols:
                    mint_to_kols[trade["contract"]] = kols

        # Fallback to audit_narratives.json for older trades without BUY kols
        if not mint_to_kols:
            for mint, data in audits.items():
                kols = data.get("kols", [])
                if kols:
                    mint_to_kols[mint] = kols

        # wallet -> list of trade results
        wallet_trades = defaultdict(list)
        trade_count = 0

        # Iterate over SELL trades that have a calculable PnL
        for trade in trades:
            if trade.get("action") != "SELL":
                continue

            pnl = trade.get("pnl_sol")
            if pnl is None:
                continue

            # The paper_trades.json uses 'contract' for SELLs, not 'mint'
            mint = trade.get("contract") or trade.get("mint")
            if not mint:
                continue

            # Look up KOLs associated with this mint in the audit narratives
            kols = mint_to_kols.get(mint, [])
            if not kols:
                continue

            trade_count += 1
            is_win = pnl > 0
            trade_info = {
                "pnl_sol": pnl,
                "is_win": is_win,
                "mint": mint,
                "ticker": trade.get("ticker", ""),
                "reason": trade.get("reason", ""),
            }

            # Attribute the trade result to every KOL involved
            for kol in kols:
                wallet_addr = kol.get("wallet")
                if wallet_addr:
                    wallet_trades[wallet_addr].append(trade_info)

        # Build wallet stats for wallets with at least MIN_CALLS trades
        wallet_stats = []
        for wallet_addr, trades_list in wallet_trades.items():
            total_calls = len(trades_list)
            if total_calls < MIN_CALLS:
                continue

            wins = sum(1 for t in trades_list if t["is_win"])
            winrate = (wins / total_calls) * 100.0
            total_pnl = sum(t["pnl_sol"] for t in trades_list)
            name = wallet_names.get(wallet_addr, "Unknown")

            wallet_stats.append({
                "address": wallet_addr,
                "name": name,
                "total_calls": total_calls,
                "winrate": round(winrate, 2),
                "total_pnl_generated": round(total_pnl, 6),
            })

        # Sort by total_pnl_generated descending (Alpha Score)
        wallet_stats.sort(key=lambda x: x["total_pnl_generated"], reverse=True)

        # Top 30 Tier 1
        tier1 = wallet_stats[:TOP_N]

        # Persist
        os.makedirs(os.path.dirname(self.tier1_file), exist_ok=True)
        with open(self.tier1_file, "w") as f:
            json.dump(tier1, f, indent=2)

        return {
            "total_analyzed": len(wallet_stats),
            "tier1_count": len(tier1),
            "tier1": tier1,
            "trades_matched": trade_count,
        }


if __name__ == "__main__":
    screener = WalletScreener()
    result = screener.run()
    print(f"\n{'=' * 60}")
    print(f"WALLET FORENSICS - ANALYSE TERMINÉE")
    print(f"{'=' * 60}")
    print(f"📊 {result['trades_matched']} SELLs avec PnL analysés")
    print(f"📈 {result['total_analyzed']} wallets retenus (min {MIN_CALLS} calls)")
    print(f"🏆 {result['tier1_count']} wallets dans le Tier 1")
    print(f"{'=' * 60}")
    print(f"\nTop 10 Tier 1 :")
    print(f"{'#':>3}  {'Nom':<20} {'Adresse':<14} {'Calls':>5} {'Winrate':>8} {'PnL (SOL)':>10}")
    print(f"   {'-'*20} {'-'*14} {'-----':>5} {'--------':>8} {'----------':>10}")
    for i, w in enumerate(result["tier1"][:10], 1):
        print(
            f"  {i:2d}. {w['name']:<20} {w['address'][:12]}... "
            f"{w['total_calls']:>5}  {w['winrate']:>7.1f}%  {w['total_pnl_generated']:+.4f}"
        )
    print(f"\n💾 Sauvegarde : {TIER1_FILE}")
    print(f"{'=' * 60}\n")