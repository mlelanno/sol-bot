import os, asyncio, aiohttp
from dotenv import load_dotenv
load_dotenv()

class RiskScanner:
    def __init__(self):
        key = os.getenv("HELIUS_API_KEY", "")
        self.rpc_url = os.getenv("HELIUS_RPC_URL") or (f"https://mainnet.helius-rpc.com/?api-key={key}" if key else "")

    async def evaluate_token(self, mint: str, mc_usd: float):
        reasons = []
        if mc_usd < 12000:
            return False, ["MC trop faible (<12k$)"]
        if not self.rpc_url:
            return True, []

        timeout = aiohttp.ClientTimeout(total=2.0)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                p_asset = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint}}
                p_large = {"jsonrpc": "2.0", "id": 2, "method": "getTokenLargestAccounts", "params": [mint]}
                r_asset, r_large = await asyncio.gather(
                    session.post(self.rpc_url, json=p_asset),
                    session.post(self.rpc_url, json=p_large),
                    return_exceptions=True
                )

                # 1. Vérification Freeze Authority
                if not isinstance(r_asset, Exception) and r_asset.status == 200:
                    d_a = await r_asset.json()
                    ownership = ((d_a.get("result") or {}).get("ownership") or {})
                    if ownership.get("frozen"):
                        reasons.append("Token gelé (Freeze actif)")

                # 2. Vérification Top 10 Holders (< 25%) & Détection de Bundling (Wallets splittés)
                if not isinstance(r_large, Exception) and r_large.status == 200:
                    d_l = await r_large.json()
                    accs = ((d_l.get("result") or {}).get("value") or [])
                    amounts = [float(a.get("uiAmount") or 0.0) for a in accs if float(a.get("uiAmount") or 0.0) > 0]
                    if len(amounts) >= 4:
                        total_supply = 1_000_000_000.0
                        # Exclure le compte #1 (Bonding Curve / LP Raydium qui détient 20-80% de la supply)
                        non_lp_top10 = amounts[1:11]
                        top10_pct = (sum(non_lp_top10) / total_supply) * 100.0
                        if top10_pct > 25.0 and mc_usd > 80_000:
                            reasons.append(f"Top 10 concentré ({top10_pct:.1f}%)")

                        # Anti-Bundling : >= 4 wallets dans le Top 10 avec montants quasi-identiques (±1.5%)
                        for i in range(len(non_lp_top10)):
                            base_amt = non_lp_top10[i]
                            if base_amt / total_supply < 0.004:
                                continue
                            similar = sum(1 for x in non_lp_top10 if abs(x - base_amt) / base_amt <= 0.015)
                            if similar >= 4:
                                reasons.append(f"Bundling détecté ({similar} wallets splittés)")
                                break
        except Exception:
            pass

        return len(reasons) == 0, reasons
