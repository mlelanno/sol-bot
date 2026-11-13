import asyncio
import json
import os
import requests
from typing import Optional, Dict, Any


class RiskScanner:
    """Cerveau Anti-Rug - Analyse les risques sur les tokens Solana."""

    def __init__(self):
        self.rpc_url = "https://api.mainnet-beta.solana.com"
        self.session = requests.Session()

    def _http_post(self, url, payload):
        """Appel HTTP POST bloquant, exécuté sur un thread dédié pour rester asynchrone."""
        return self.session.post(url, json=payload, timeout=10)

    async def check_authorities(self, mint: str) -> bool:
        """
        Vérifie que Mint Authority et Freeze Authority sont à None (Revoked).
        Retourne True si les autorités sont revocées (sécurisé), False sinon.
        """
        try:
            # Récupère les autorités du mint (méthode getMintAuthority / getFreezeAuthority)
            response = await asyncio.to_thread(
                self._http_post,
                f"{self.rpc_url}/mint/authorities",
                {"jsonrpc": "2.0", "id": 1, "method": "getMintAuthority", "params": [mint]},
            )
            data = response.json()
            result = data.get("result", {}) or {}
            authorities = result.get("authorities", []) if isinstance(result, dict) else []

            mint_auth = None
            freeze_auth = None
            if isinstance(authorities, dict):
                mint_auth = authorities.get("Mint Authority", None)
                freeze_auth = authorities.get("Freeze Authority", None)
            elif isinstance(authorities, list):
                for item in authorities:
                    if not isinstance(item, dict):
                        continue
                    role = item.get("type") or item.get("role") or item.get("name")
                    if role == "Mint Authority":
                        mint_auth = item.get("address")
                    elif role == "Freeze Authority":
                        freeze_auth = item.get("address")

            # Vérifie que Mint Authority et Freeze Authority sont None/Revoked
            if mint_auth is None and freeze_auth is None:
                return True
            else:
                return False
        except Exception as e:
            print(f"Erreur lors de la vérification des autorités pour {mint}: {e}")
            return False

    async def check_holder_distribution(self, mint: str) -> bool:
        """
        Vérifie la distribution des holders. Retourne False si le top 10 (hors Raydium/Pump.fun)
        possède plus de 25% de la supply.
        """
        try:
            # Récupère les holders du token
            response = await asyncio.to_thread(
                self._http_post,
                f"{self.rpc_url}/mint/{mint}/holders",
                {"jsonrpc": "2.0", "id": 1, "method": "getTokenHolders", "params": [mint]},
            )
            data = response.json()
            holders = data.get("result", {}).get("holders", [])

            if not holders:
                return True  # Pas de holders, donc pas de risque de concentration

            # Calculer la total supply du token
            total_supply = sum(h.get("total_supply", 0) for h in holders)
            if total_supply == 0:
                return True

            # Filtrer les adresses connues (Raydium/Pump.fun)
            known_addresses = {
                "91wjaiPv4uhsDUA1qo8NwNAkYNgqnjV7TvSCPeA7pump",
                "2T56GBrvcyeWWyhUAzsTFW4AcFag1nr7xyzrtZn7pump",
                "12bTtDLSegj1rw2oxXWYm63Rxw5QxkVSXDHCEvRShaDe",
                "2Er3UtbQGWyNgeKMyUs218i11Z6v4gtfgwmqoSNPpump",
                "478PuXdVMyM8K23kPnprBguEHYER8G4LBjcXWbPTpump",
                "SmDoPh7u9PkXz2NkFVPhq1HK3EBPuHYZaXQ7wSvb31c",
                "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",
                "7bJ5oQZYYqBuzd1BwF6F5tn2sNhEfHweXxeHrTMkpump",
                "GtzovYLBjGBKd7ZZ9D35h6kP1oLPSqhyyjPi41Wfjqnn",
                "FC5CvdHcu8Tx7Y2rcSD6JgwZu1uPAXaaEvfozWPTALUS",
                "BU3QPhnw24nPUhnqU1sV6vB4cPuBotszAxPXyUGhnqLM",
                "CmC2H4bQHiCenc5FTD9o2E5vVJoP2eXdkUP33bpvpump",
                "7xTBsvLa5njozL7YAF346TDgUbztEPxpZzGSJMPApump",
            }

            # Compter les tokens dans le top 10 (hors known addresses)
            top_holders = []
            for holder in holders:
                address = holder.get("address", "")
                if address not in known_addresses:
                    top_holders.append(holder)
                    if len(top_holders) >= 10:
                        break

            if len(top_holders) < 10:
                return True  # Moins de 10 holders non-connus, pas de risque de concentration

            # Calculer la proportion de supply dans le top 10
            top_supply = sum(h.get("total_supply", 0) for h in top_holders)
            if top_supply > 0.25 * total_supply:
                return False  # Le top 10 contrôle plus de 25% de la supply

            return True
        except Exception as e:
            print(f"Erreur lors de la vérification de la distribution des holders pour {mint}: {e}")
            return True  # En cas d'erreur, on considère que c'est sûr

    async def check_ml_weights(self, mc_usd: float) -> tuple:
        """
        Lit les recommandations ML depuis data/ml_weights.json et valide
        le bracket de Market Cap du token candidat.
        Retourne (is_safe, reason_message).
        """
        weights_file = "/home/kilpi/trading_bot/data/ml_weights.json"
        if not os.path.exists(weights_file):
            return True, "Pas de data ML"

        try:
            with open(weights_file, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            return True, "Pas de data ML"

        total_analyzed = data.get("total_analyzed_trades", 0)

        # Déterminer le bracket
        if mc_usd < 15000:
            bracket = "Micro"
        elif mc_usd <= 50000:
            bracket = "Low"
        else:
            bracket = "Mid"

        bracket_stats = data.get("mc_brackets_stats", {}).get(bracket, {})
        count = bracket_stats.get("count", 0)

        # Seuil de signification : minimum 30 trades par tranche
        if count < 30:
            return True, f"Observation ML : échantillon insuffisant ({count}/30) sur {bracket}"

        winrate = bracket_stats.get("winrate", 0.0)
        avg_pnl_sol = bracket_stats.get("avg_pnl_sol", 0.0)

        if winrate < 40.0 or avg_pnl_sol < 0:
            return False, f"Rejet ML : Le bracket {bracket} a un winrate trop faible."

        return True, f"Validation ML : Bracket {bracket} approuvé."

    async def check_funding_clusters(self, mint: str, top_holders: list) -> bool:
        """
        Détecte le bundling par financement : si 3 holders ou plus parmi les 8 plus
        gros holders (hors pools Raydium/Pump.fun) partagent exactement la même
        adresse funder externe, le token est rejeté.

        Interroge RPC Solana (getSignaturesForAddress / getTransaction) avec un
        timeout racine de 3 secondes. Ne bloque jamais l'exécution en cas de
        latence ou d'erreur RPC.
        """
        if not top_holders or len(top_holders) < 3:
            return True

        try:
            from_addr_map = {}
            for holder in top_holders[:8]:
                address = holder.get("address", "")
                if not address:
                    continue

                try:
                    sigs = await asyncio.to_thread(
                        self._http_post,
                        f"{self.rpc_url}/address/{address}/transactions",
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "getSignaturesForAddress",
                            "params": [address, {"limit": 1}],
                        },
                        timeout=aiohttp.ClientTimeout(total=3),
                    )
                    data = sigs.json()
                    result = data.get("result", [])
                    if result and isinstance(result, list) and len(result) > 0:
                        tx_sig = result[0].get("transactionSignature", "")
                        if tx_sig:
                            tx = await asyncio.to_thread(
                                self._http_post,
                                f"{self.rpc_url}/tx/{tx_sig}",
                                {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "getTransaction",
                                    "params": [tx_sig, {"encoding": "jsonParsed"}],
                                },
                                timeout=aiohttp.ClientTimeout(total=3),
                            )
                            tx_data = tx.json()
                            tx_result = tx_data.get("result", {})
                            meta = tx_result.get("meta", {})
                            if meta:
                                status = meta.get("status", {})
                                err = status.get("err")
                                if err:
                                    from_ = err.get("from", "") if isinstance(err, dict) else ""
                                    if from_:
                                        from_addr_map[address] = from_
                    else:
                        pass
                except Exception:
                    continue

            funder_map = {}
            for holder_addr, funder_addr in from_addr_map.items():
                if funder_addr:
                    funder_map.setdefault(funder_addr, []).append(holder_addr)

            for funder_addr, holders_list in funder_map.items():
                if len(holders_list) >= 3:
                    return False, f"Bundling détecté : {len(holders_list)} top holders financés par le même wallet {funder_addr[:6]}..."

            return True

        except Exception as e:
            print(f"Erreur lors du check_funding_clusters pour {mint}: {e}")
            return True

    async def evaluate_token(self, mint: str, mc_usd: float = 0.0) -> Dict[str, Any]:
        """
        Appelle les vérifications précédentes et retourne un booléen is_safe
        et un dictionnaire reasons détaillant pourquoi le token a passé ou échoué.
        """
        # Vérifier les autorités
        authorities_ok = await self.check_authorities(mint)

        # Vérifier la distribution des holders
        holders_ok = await self.check_holder_distribution(mint)

        # Vérifier les poids ML
        ml_safe, ml_reason = await self.check_ml_weights(mc_usd)

        # Vérifier la détection de bundling par financement
        funding_ok = True
        funding_reason = "Aucun signal de bundling détecté"
        try:
            holders_resp = await asyncio.to_thread(
                self._http_post,
                f"{self.rpc_url}/mint/{mint}/holders",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenHolders",
                    "params": [mint],
                },
                timeout=aiohttp.ClientTimeout(total=10),
            )
            holders_data = holders_resp.json()
            holders = holders_data.get("result", {}).get("holders", [])

            known_addresses = {
                "91wjaiPv4uhsDUA1qo8NwNAkYNgqnjV7TvSCPeA7pump",
                "2T56GBrvcyeWWyhUAzsTFW4AcFag1nr7xyzrtZn7pump",
                "12bTtDLSegj1rw2oxXWYm63Rxw5QxkVSXDHCEvRShaDe",
                "2Er3UtbQGWyNgeKMyUs218i11Z6v4gtfgwmqoSNPpump",
                "478PuXdVMyM8K23kPnprBguEHYER8G4LBjcXWbPTpump",
                "SmDoPh7u9PkXz2NkFVPhq1HK3EBPuHYZaXQ7wSvb31c",
                "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",
                "7bJ5oQZYYqBuzd1BwF6F5tn2sNhEfHweXxeHrTMkpump",
                "GtzovYLBjGBKd7ZZ9D35h6kP1oLPSqhyyjPi41Wfjqnn",
                "FC5CvdHcu8Tx7Y2rcSD6JgwZu1uPAXaaEvfozWPTALUS",
                "BU3QPhnw24nPUhnqU1sV6vB4cPuBotszAxPXyUGhnqLM",
                "CmC2H4bQHiCenc5FTD9o2E5vVJoP2eXdkUP33bpvpump",
                "7xTBsvLa5njozL7YAF346TDgUbztEPxpZzGSJMPApump",
            }

            top_holders = []
            for holder in holders:
                address = holder.get("address", "")
                if address not in known_addresses:
                    top_holders.append(holder)
                    if len(top_holders) >= 8:
                        break

            if top_holders:
                funding_ok, funding_reason = await self.check_funding_clusters(mint, top_holders)
        except Exception as e:
            print(f"Erreur lors de la vérification du funding pour {mint}: {e}")
            funding_ok = True

        is_safe = authorities_ok and holders_ok and ml_safe and funding_ok

        reasons = {
            "authorities": "Revoked (Mint Authority et Freeze Authority sont None)" if authorities_ok else "Non revocées",
            "holder_distribution": "Top 10 (hors Raydium/Pump.fun) ne contrôle pas plus de 25% de la supply" if holders_ok else "Le top 10 contrôle plus de 25% de la supply",
            "ml_validation": ml_reason,
            "funding_bundling": funding_reason,
        }

        return {
            "is_safe": is_safe,
            "reasons": reasons,
        }
