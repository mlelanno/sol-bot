import json
import os
from datetime import datetime


TRADES_FILE = "/home/kilpi/trading_bot/logs/paper_trades.json"
ACTIVE_POSITIONS_FILE = "/home/kilpi/trading_bot/data/active_positions.json"


class PaperTradingEngine:
    def __init__(self):
        self.sol_balance = 2.0
        self.trade_size = 0.05
        self.slippage = 0.025
        self.fees_sol = 0.002
        os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
        os.makedirs(os.path.dirname(ACTIVE_POSITIONS_FILE), exist_ok=True)

        if not os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, "w") as f:
                json.dump([], f)
        if not os.path.exists(ACTIVE_POSITIONS_FILE):
            with open(ACTIVE_POSITIONS_FILE, "w") as f:
                json.dump({}, f)

    def _load_positions(self):
        try:
            with open(ACTIVE_POSITIONS_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_positions(self, positions):
        with open(ACTIVE_POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)

    async def execute_buy(
        self,
        contract_address: str,
        ticker: str,
        price_usd: float,
        mc_usd: float,
        vol_usd: float,
    ):
        """Exécute un achat avec vérification de solde, frais et slippage."""

        # Vérification du solde: besoin de trade_size + fees
        required_sol = self.trade_size + self.fees_sol
        if self.sol_balance < required_sol:
            return False, f"Solde SOL insuffisant: besoin de {required_sol} SOL, disponible {round(self.sol_balance, 4)} SOL"

        # Application du slippage à l'entrée (achat plus cher)
        price_with_slippage = price_usd * (1 + self.slippage)

        # Déduction des frais et de la position du solde
        self.sol_balance -= required_sol

        # Calcul des tokens achetés
        tokens_held = self.trade_size / price_usd

        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "BUY",
            "ticker": ticker,
            "contract": contract_address,
            "entry_price_usd": price_usd,
            "price_with_slippage": price_with_slippage,
            "amount_sol": self.trade_size,
            "network_fees_sol": self.fees_sol,
            "market_cap": mc_usd,
            "volume_24h": vol_usd,
            "remaining_sol": round(self.sol_balance, 4),
        }

        # Enregistrement du trade
        with open(TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

        # Mise à jour des positions actives
        position_data = {
            "mint": contract_address,
            "ticker": ticker,
            "entry_price_usd": price_usd,
            "tokens_held": tokens_held,
            "sol_invested": self.trade_size,
            "entry_timestamp": datetime.now().timestamp(),
            "tp1_executed": False,
        }

        positions = self._load_positions()
        positions[contract_address] = position_data
        self._save_positions(positions)

        return True, trade_record

    async def execute_sell(
        self,
        contract_address: str,
        ratio_to_sell: float,
        current_price_usd: float,
        reason: str,
    ):
        """Exécute une vente avec slippage à la sortie et frais."""

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

        # Valeur marchande des tokens vendus (après slippage)
        price_with_slippage = current_price_usd * (1 - self.slippage)
        sol_recovered = tokens_to_sell * price_with_slippage

        # Ajout du SOL récupéré au balance (décrit des frais)
        self.sol_balance += sol_recovered - self.fees_sol

        # Calcul du PnL
        pnl_sol = sol_recovered - self.fees_sol - (tokens_to_sell * entry_price)
        pnl_percentage = ((current_price_usd / entry_price) - 1) * 100

        # Création de l'enregistrement de la transaction
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "SELL",
            "ticker": position["ticker"],
            "contract": contract_address,
            "reason": reason,
            "entry_price_usd": entry_price,
            "exit_price_usd": current_price_usd,
            "price_with_slippage": price_with_slippage,
            "tokens_sold": round(tokens_to_sell, 6),
            "sol_recovered": round(sol_recovered, 6),
            "network_fees_sol": self.fees_sol,
            "pnl_sol": round(pnl_sol, 6),
            "pnl_percent": round(pnl_percentage, 2),
            "remaining_tokens": round(tokens_restants, 6),
        }

        # Enregistrement du trade
        with open(TRADES_FILE, "r") as f:
            trades = json.load(f)
        trades.append(trade_record)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

        # Mise à jour de la position
        if ratio_to_sell == 1.0 or tokens_restants <= 0:
            # Clôture totale : suppression de la position
            del positions[contract_address]
        else:
            # Mise à jour de la position restante
            positions[contract_address]["tokens_held"] = round(tokens_restants, 6)
            positions[contract_address]["tp1_executed"] = True

        self._save_positions(positions)

        details = {
            "action": "SELL",
            "contract": contract_address,
            "entry_price_usd": entry_price,
            "exit_price_usd": current_price_usd,
            "price_with_slippage": price_with_slippage,
            "tokens_sold": round(tokens_to_sell, 6),
            "sol_recovered": round(sol_recovered, 6),
            "network_fees_sol": self.fees_sol,
            "pnl_sol": round(pnl_sol, 6),
            "pnl_percent": round(pnl_percentage, 2),
            "remaining_tokens": round(tokens_restants, 6),
            "reason": reason,
        }

        return True, f"Succès : {details['sol_recovered']} SOL récupérés ({details['pnl_percent']:.2f}% de PnL)", details

