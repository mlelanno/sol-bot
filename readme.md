# SOL Smart Money Bot 🎯

Un bot de trading algorithmique à ultra-haute fréquence sur la blockchain Solana, conçu pour tracker les mouvements de portefeuilles "Smart Money" (KOLs, Insiders) en temps réel.

## 🚀 Architecture

1. **Helius Webhook Listener** (`agents/helius_listener.py`) : Capte les transactions (SWAP et TRANSFER) d'une liste de portefeuilles cibles en quelques millisecondes via un tunnel Cloudflare.
2. **Consensus Engine** : Analyse les flux et déclenche un achat (Paper Trading) si `N` KOLs achètent le même token dans une fenêtre de `T` secondes.
3. **Position Manager** (`agents/position_manager.py`) : Surveille le PnL en direct via l'API DexScreener et applique des règles mathématiques strictes (Stop-Loss à -30%, Take-Profit 1 à +100%).
4. **Web Dashboard** (`tools/web_dashboard.py`) : Interface utilisateur (TUI local) pour monitorer les performances en temps réel, les graphiques et les logs.

## 🛠️ Installation & Démarrage

### Prérequis
- Python 3.10+
- Un compte Helius (API Key)
- Tunnel Cloudflare (`cloudflared`) pour exposer le webhook local.

### Configuration
1. Clonez le dépôt.
2. Créez un fichier `.env` à la racine contenant :
   ```env
   HELIUS_API_KEY=votre_cle_api
   TELEGRAM_BOT_TOKEN=optionnel
   TELEGRAM_CHANNEL_ID=optionnel
   ```
3. Installez les dépendances : `pip install aiohttp rich`

### Lancement des processus

Lancez les 3 processus en arrière-plan :

```bash
# 1. Le Listener Helius
nohup python3 -u agents/helius_listener.py > logs/helius_listener.log 2>&1 &

# 2. Le Gestionnaire de Positions (TP/SL)
nohup python3 -u agents/position_manager.py > logs/position_manager.log 2>&1 &

# 3. L'Interface Web
nohup python3 -u tools/web_dashboard.py > logs/web_dashboard.log 2>&1 &
```

Accédez ensuite au terminal de trading via `http://localhost:8080`.

## 📈 Mathématiques (Règles actuelles)
- **Capital initial** : 2.0 SOL (Paper Trading)
- **Taille de position** : 0.05 SOL
- **Take Profit 1** : +100% (Vente de 50%)
- **Stop Loss** : -30% (Vente totale)