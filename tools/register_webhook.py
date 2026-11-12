#!/usr/bin/env python3
"""
Enregistrement du webhook Helius via l'API Cloudflare Tunnel.
Usage: python tools/register_webhook.py
"""

import json
import os
import sys

def get_tunnel_url():
    """Obtient l'URL du tunnel Cloudflare."""
    # Méthode 1 : Lire depuis une variable d'environnement ou fichier config
    env_url = os.environ.get('CLOUDFLARE_TUNNEL_URL')
    if env_url:
        return env_url
    
    # Méthode 2 : Chercher dans les logs (si URL trycloudflare.com générée)
    log_path = '/home/kilpi/trading_bot/logs/cloudflared.log'
    import re
    from pathlib import Path
    if Path(log_path).exists():
        content = Path(log_path).read_text(errors='ignore')
        pattern = r'https://[a-z0-9_-]+\.(?:try)?cloudflare\.com[^\s]*'
        url_match = re.search(pattern, content)
        if url_match and 'developers.cloudflare.com' not in url_match.group():
            return url_match.group()
    
    # Fallback : localhost (mode de développement/non-production)
    return None

def main():
    # Charger HELIUS_API_KEY
    env_path = '/home/kilpi/trading_bot/.env'
    with open(env_path) as f:
        for line in f:
            if line.startswith('HELIUS_API_KEY='):
                helius_api_key = line.strip().split('=', 1)[1]
                break
    
    # Charger smart wallets
    wallets_path = '/home/kilpi/trading_bot/data/smart_wallets.json'
    with open(wallets_path) as f:
        wallets_data = json.load(f)
    
    account_addresses = [wallet['address'] for wallet in wallets_data]
    
    print("="*60)
    print("📡 Configuration Helius Webhook")
    print("="*60)
    print(f"✓ HELIUS_API_KEY : {helius_api_key[:20]}...")
    print(f"✓ Smart wallets configurées : {len(account_addresses)}")
    
    # Obtenir l'URL du tunnel
    public_tunnel_url = get_tunnel_url()
    
    if not public_tunnel_url:
        print("\n⚠️  PAS D'URL CLOUDFLARE TROUVÉE")
        print("   Configurez CLOUDFLARE_TUNNEL_URL ou utilisez --hostname")
        sys.exit(1)
    
    webhook_url = f"{public_tunnel_url}/webhook"
    print(f"\n🔗 Webhook URL cible : {webhook_url}")
    
    # Préparer la requête POST à Helius
    payload = {
        "webhookURL": webhook_url,
        "transactionTypes": ["SWAP"],
        "accountAddresses": account_addresses,
        "webhookType": "enhanced"
    }
    
    # Envoyer la requête à Helius
    import urllib.request
    try:
        print(f"\n📤 Envoi de l'enregistrement webhook...")
        req = urllib.request.Request(
            f"https://api.helius.xyz/v0/webhooks?api-key={helius_api_key}",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✅ Webhook enregistré !")
            print(f"   ID Helius : {result.get('id')}")
            print(f"   URL confirmée : {webhook_url}")
            print(f"   Transaction types : {payload['transactionTypes']}")
            print(f"   Accounts surveillés : {len(payload['accountAddresses'])}")
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"\n❌ ÉCHEC d'enregistrement Helius")
        print(f"   Code HTTP : {e.code}")
        print(f"   Message : {error_body[:200]}")
        return None
    except Exception as e:
        print(f"\n❌ Erreur réseau : {e}")
        return None

if __name__ == '__main__':
    main()
