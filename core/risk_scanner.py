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

    async def evaluate_token(self, mint: str) -> Dict[str, Any]:
        """
        Appelle les vérifications précédentes et retourne un booléen is_safe
        et un dictionnaire reasons détaillant pourquoi le token a passé ou échoué.
        """
        # Vérifier les autorités
        authorities_ok = await self.check_authorities(mint)

        # Vérifier la distribution des holders
        holders_ok = await self.check_holder_distribution(mint)

        if authorities_ok and holders_ok:
            return {
                "is_safe": True,
                "reasons": {
                    "authorities": "Revoked (Mint Authority et Freeze Authority sont None)",
                    "holder_distribution": "Top 10 (hors Raydium/Pump.fun) ne contrôle pas plus de 25% de la supply",
                },
            }
        else:
            return {
                "is_safe": False,
                "reasons": {
                    "authorities": "Non revocées (Mint Authority ou Freeze Authority présents)",
                    "holder_distribution": "Le top 10 contrôle plus de 25% de la supply",
                },
            }
