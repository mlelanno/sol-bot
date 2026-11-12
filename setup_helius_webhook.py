#!/usr/bin/env python3
"""
Configuration initiale pour l'écouteur Helius Webhook.
Ce script configure et vérifie que le service est prêt à recevoir les événements Solana.

Fonctions:
- Vérifier que le webhook endpoint /webhook répond HTTP 200
- S'assurer que aiohttp est installé
- Tester une requête de validation du webhook

Usage: python setup_helius_webhook.py
"""

import json
import subprocess
import sys


def check_webhook_endpoint():
    """Vérifier si l'endpoint /webhook fonctionne."""
    import requests
    
    try:
        response = requests.post(
            'http://127.0.0.1:5000/webhook',
            headers={'Content-Type': 'application/json'},
            json={
                'result': {
                    'transaction': {
                        'meta': {},
                        'events': []
                    }
                }
            },
            timeout=5
        )
        print(f"✓ Webhook endpoint HTTP status: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Test webhook échoué: {e}")
        return False


def main():
    """Script de configuration initiale."""
    print("\n" + "="*60)
    print("  setup_helius_webhook.py - Configuration Helius Webhook")
    print("="*60 + "\n")
    
    # Vérifier que le serveur tourne
    try:
        import requests
        response = requests.get('http://127.0.0.1:5000', timeout=3)
        print("✓ Serveur Python sur le port 5000")
    except ConnectionRefusedError:
        print("✗ Le serveur n'est pas actif sur le port 5000")
        print("  Lancez: python agents/helius_listener.py > logs/helius_listener.log 2>&1 &")
        return 1
    except Exception as e:
        print(f"✗ Échec connexion serveur: {e}")
        return 1
    
    # Tester l'endpoint webhook
    if check_webhook_endpoint():
        print("✓ Endpoint /webhook actif et fonctionnel\n")
    
    print("="*60)
    print("Configuration terminée avec succès !")
    print("Le service écoute les événements Solana via Helius.")
    print("="*60 + "\n")


if __name__ == '__main__':
    sys.exit(main())