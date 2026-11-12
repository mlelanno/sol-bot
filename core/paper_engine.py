import json
import os
from datetime import datetime

TRADES_FILE = "/home/kilpi/trading_bot/logs/paper_trades.json"
ACTIVE_POSITIONS_FILE = "/home/kilpi/trading_bot/data/active_positions.json"

class PaperTradingEngine:
    def __init__(self, initial_sol=1.0, trade_size_sol=0.05, slippage=0.15):
        self.sol_balance = initial_sol
        self.trade_size = trade_size_sol
        self.slippage = slippage
        os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
        os.makedirs(os.path.dirname(ACTIVE_POSITIONS_FILE), exist_ok=True)
        
        # Initialisation des trades et positions actives
        if not os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, "w") as f:
                json.dump([], f)
        if not os.path.exists(ACTIVE_POSITIONS_FILE):
            with open(ACTIVE_POSITIONS_FILE, "w") as f:
                json.dump({}, f)

    def _load_positions(self):
        """Charge les positions actives depuis le fichier JSON."""
        try:
            with open(ACTIVE_POSITIONS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_positions(self, positions):
        """Sauvegarde les positions actives dans le fichier JSON."""
        with open(ACTIVE_POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)

    def execute_buy(self, contract_address: str, ticker: str, price_usd: float, mc_usd: float, vol_usd: float):
        if self.sol_balance < self.trade_size:
            return False, "Solde SOL insuffisant"

        effective_price = price_usd * (1 + self.slippage)
        self.sol_balance -= self.trade_size

        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "BUY",
            "ticker": ticker,
            "contract": contract_address,
            "entry_price_usd": price_usd,
            "executed_price_usd": effective_price,
            "amount_sol": self.trade_size,
            "market_cap": mc_usd,
            "volume_24h": vol_usd,
            "remaining_sol": round(self.sol_balance, 4)
        }

        with open(TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

        # Calcul du nombre de tokens achetés (prix en USD, investiment en SOL)
        tokens_held = self.trade_size / price_usd
        sol_invested = self.trade_size  # SOL investi pour l'entrée
        
        position_data = {
            "mint": contract_address,
            "ticker": ticker,
            "entry_price_usd": price_usd,
            "tokens_held": tokens_held,
            "sol_invested": sol_invested,
            "entry_timestamp": datetime.now().timestamp(),
            "tp1_executed": False
        }

        # Mise à jour des positions actives
        positions = self._load_positions()
        positions[contract_address] = position_data
        self._save_positions(positions)

        return True, trade_record

    def execute_sell(self, contract_address, ratio_to_sell, current_price_usd, reason):
        """
        Vends une partie ou la totalité des tokens d'une position.
        
        Args:
            contract_address: Adresse du contrat du token
            ratio_to_sell: 0.5 (vendre 50%) ou 1.0 (clôture totale)
            current_price_usd: Prix actuel en USD
            reason: Motif de la vente ("STOP_LOSS", "TAKE_PROFIT")
            
        Returns:
            Tuple (success, message, details)
        """
        # Charger les positions actives
        positions = self._load_positions()
        
        if contract_address not in positions:
            return False, f"Position introuvable pour {contract_address}", None

        position = positions[contract_address]
        entry_price = position["entry_price_usd"]
        tokens_held = position["tokens_held"]
        sol_invested = position["sol_invested"]
        
        # Calcul des tokens à vendre et restants
        tokens_to_sell = tokens_held * ratio_to_sell
        tokens_restants = tokens_held - tokens_to_sell
        
        # Le SOL récupéré est basé sur la valeur marchande des tokens vendus
        sol_recovered = tokens_to_sell * current_price_usd
        
        # Ajouter le SOL récupéré au balance (pour la vente partielle, on ajoute uniquement ce qui est vendu)
        self.sol_balance += sol_recovered
        
        # Créer l'enregistrement de la transaction
        pnl_sol = sol_recovered - (tokens_to_sell * entry_price)
        pnl_percentage = ((current_price_usd / entry_price) - 1) * 100
        
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "SELL",
            "ticker": position["ticker"],
            "contract": contract_address,
            "reason": reason,
            "entry_price_usd": entry_price,
            "exit_price_usd": current_price_usd,
            "tokens_sold": round(tokens_to_sell, 6),
            "sol_recovered": round(sol_recovered, 6),
            "pnl_sol": round(pnl_sol, 6),
            "pnl_percent": round(pnl_percentage, 2),
            "remaining_tokens": round(tokens_restants, 6)
        }

        with open(TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

        # Mise à jour de la position si vente partielle
        if ratio_to_sell == 1.0 or tokens_restants <= 0:
            # Clôture totale : suppression de la position
            del positions[contract_address]
        else:
            # Mise à jour de la position restante
            position["tokens_held"] = round(tokens_restants, 6)
            position["tp1_executed"] = True

        self._save_positions(positions)

        details = {
            "action": "SELL",
            "contract": contract_address,
            "tokens_sold": round(tokens_to_sell, 6),
            "sol_recovered": round(sol_recovered, 6),
            "pnl_sol": round(pnl_sol, 6),
            "pnl_percent": round(pnl_percentage, 2),
            "remaining_tokens": round(tokens_restants, 6),
            "reason": reason
        }

        return True, f"Succès : {details['sol_recovered']} SOL récupérés ({details['pnl_percent']:.2f}% de PnL)", details
