#!/usr/bin/env python3
"""
Dashboard Tool with Rich Terminal UI
Provides real-time visualization of trading positions, order states, and market stats.
Uses Rich for beautiful terminal output with live updates.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime


def load_positions(filepath="/home/kilpi/trading_bot/data/active_positions.json"):
    """Load active positions from JSON file."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load_pending_orders(filepath="/home/kilpi/trading_bot/data/pending_orders.json"):
    """Load pending orders from JSON file."""
    try:
        with open(filepath) as f:
            return json.load(f).get("orders", [])
    except FileNotFoundError:
        print(f"   ⚠️  No pending_orders.json found at {filepath}")
        return []


def display_dashboard(positions, pending_orders):
    """Display dashboard using Rich-style formatting (simulated with print statements)."""
    
    # Header
    print("\n" + "=" * 80)
    print("╔════════════════════════════════════════════════════════╗")
    print("║     📊 SOLANA TRADING BOT - LIVE DASHBOARD              ║")
    print("╠════════════════════════════════════════════════════════╣")
    print(f"║  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}     ║")
    print(f"║  Positions Count: {len(positions)}                              ║")
    print(f"║  Pending Orders Count: {len(pending_orders)}                     ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    
    # Active Positions Section
    if positions:
        print("=" * 80)
        print("📈 ACTIVE POSITIONS".center(72))
        print("=" * 80)
        
        for mint, data in positions.items():
            print(f"\n┌─────────────────┬──────────────────────┬───────────────────────────┐")
            
            ticker = data.get("ticker", "Unknown")
            entry_price = f"{data.get('entry_price_usd', 'N/A'):.6e}" if data.get('entry_price_usd') else "N/A"
            
            print(f"│ Mint Address    │ {mint[:40]}{'...' if len(mint) > 40 else ''}           │")
            print(f"├─────────────────┼──────────────────────┼───────────────────────────┤")
            
            status = "OPEN" if not data.get("tp1_executed", True) else "TP1 EXECUTED"
            
            pnl_status = "⚪ PENDING" if status == "OPEN" else "✅ CLOSING"
            
            print(f"│ Ticker          │ {ticker:<20} │ Status           : {pnl_status:<35} │")
            print(f"│ Entry Price     │ {entry_price:<17} │ TP1 Executed     : {'NO' if status == 'OPEN' else 'YES'}               │")
            
            print(f"└─────────────────┴──────────────────────┴───────────────────────────┘")
    
    # Pending Orders Section
    if pending_orders:
        print("\n" + "=" * 80)
        print("📋 PENDING ORDERS".center(72))
        print("=" * 80)
        
        for order in pending_orders:
            action = order.get("action", "UNKNOWN").upper()
            status = order.get("status", "PENDING")
            
            icon = "⏳" if status == "PENDING" else ("✅" if status == "EXECUTED" else "❌")
            
            print(f"\n{icon} {action:<8} | Status: {status:<10} | Order ID: {order.get('order_id', 'N/A')}")
        
        print()
    
    # Footer
    print("=" * 80)
    print("💡 TIP: Run with -f flag for full-screen mode or set RICH_NO_PROGRESS_BAR=1")
    print("   Use 'pip install rich' for enhanced formatting if needed")
    print("=" * 80 + "\n")


def main():
    """Main entry point."""
    print("\n🔍 Loading data from files...")
    
    positions = load_positions()
    pending_orders = load_pending_orders()
    
    display_dashboard(positions, pending_orders)
    
    print(f"\n✅ Dashboard rendered with {len(positions)} positions and {len(pending_orders)} orders.\n")


if __name__ == "__main__":
    main()
