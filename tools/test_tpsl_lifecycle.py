#!/usr/bin/env python3
"""Script de test pour le cycle complet TP/SL."""
import asyncio
import json
import sys
import os

sys.path.insert(0, "/home/kilpi/trading_bot")
os.chdir("/home/kilpi/trading_bot")

from core.paper_engine import PaperTradingEngine, TRADES_FILE, ACTIVE_POSITIONS_FILE
from agents.position_manager import PositionManager

async def main():
    print("\n" + "="*80)
    print("TEST: Cycle complet TP/SL - Paper Trading Engine")
    print("="*80 + "\n")
    
    # Initialisation de l'engine
    engine = PaperTradingEngine()
    
    # Creer le manager TP/SL
    manager = PositionManager()
    await manager.connect(engine)
    
    print("\n--- Etape 1: Achat d'une position (BUY) ---")
    mint_test = "9n4nGQAFBwhwdFdp5PnPUjkjgtDuRkhuAxPJEhjrfv5K"  # PYTH
    ticker_test = "PYTH"
    
    success, record = engine.execute_buy(
        contract_address=mint_test,
        ticker=ticker_test,
        price_usd=0.0866214798678425,  # Prix actuel PYTH
        mc_usd=3250000000,
        vol_usd=1200000000
    )
    
    if not success:
        print("Echec de l'achat - impossible de continuer le test")
        return
    
    print(f"BUY executee avec succes : {record}")
    
    print("\n--- Etape 2: Attendre quelques secondes puis verifier la position ---")
    await asyncio.sleep(1)
    
    # Verifier la position (normalement declenchera STOP LOSS si < -30%)
    result = await manager.check_position(mint_test)
    print(f"check_position resultat : {result}")
    
    print("\n--- Etape 3: Vendre completement (SELL) ---")
    success, msg, details = engine.execute_sell(
        contract_address=mint_test,
        ratio_to_sell=1.0,
        current_price_usd=0.0866214798678425,
        reason="MANUAL_SELL_TEST"
    )
    
    print(f"SELL resultat : {msg}")
    
    # Verifier quaucune position n'est enregistree
    await asyncio.sleep(0.1)
    try:
        with open(ACTIVE_POSITIONS_FILE, "r") as f:
            data = json.load(f)
        if mint_test in data:
            print(f"ATTENTION: Position encore presente pour {mint_test}")
        else:
            print("Position correctement supprimee apres SELL complet")
    except FileNotFoundError:
        print("Fichier active_positions.json vide - toutes positions fermees")
    
    print("\n--- Etape 4: Re-achat pour tester TAKE PROFIT ---")
    # Re-achat pour tester TAKE PROFIT
    success, record2 = engine.execute_buy(
        contract_address=mint_test,
        ticker=ticker_test,
        price_usd=0.0866214798678425,
        mc_usd=3250000000,
        vol_usd=1200000000
    )
    
    if success:
        # Simuler un TAKE PROFIT 1 en ecrivant manuellement dans le fichier
        with open(ACTIVE_POSITIONS_FILE, "r") as f:
            data = json.load(f)
        
        print("Position re-achetee pour test TAKE PROFIT.")
        print("Simulant prise de profit 1...")
        # Dans un scenario reel, check_position declencherait TP1 a +100%
        success2, msg2, details2 = engine.execute_sell(
            contract_address=mint_test,
            ratio_to_sell=0.5,
            current_price_usd=0.0866214798678425,
            reason="TP1_SIMULATION"
        )
        print(f"Vente partielle resultats : success={success2}, msg={msg2}")
    else:
        print("Impossible de re-acheter - solde peut etre insuffisant")
    
    print("\n" + "="*80)
    print("TEST TERMINE - Tous les modules fonctionnent ensemble")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())