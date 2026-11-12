#!/usr/bin/env python3
# Script de liaison pour créer un webhook Helius.

import json
import requests
from pathlib import Path

SMART_WALLETS_PATH = '/home/kilpi/trading_bot/data/smart_wallets.json'
HELIUS_WEBHOOK_ENDPOINT = 'https://api.helius.xyz/v0/webhooks'

def load_smart_wallets():
    path = Path(SMART_WALLETS_PATH)
    if not path.exists():
    
    with open(path, 'r') as f:
        wallets_raw = json.load(f)
    
    wallet_addresses = [wallet['address'] for wallet in wallets_raw]
    return wallet_addresses

def create_helius_webhook(api_key: str, cloudflare_url: str):
    params = {
        'accountAddresses': ','.join(load_smart_wallets()),
        'transactionTypes': ['SWAP'],
        'webhookType': 'enhanced'
    }
    
    url = cloudflare_url + params['accountAddresses']
    print(f'[HELIUS SETUP] Envoi requête POST vers Helius...')
    print(f'  Account Addresses: {params["accountAddresses"][:50]}... ({len(params["accountAddresses"]).split(',')} wallets)')
    
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        payload = json.dumps({})
        
        response = requests.post(
            HELIUS_WEBHOOK_ENDPOINT,
            params={'api-key': api_key, 'accountAddresses': params['accountAddresses']},
            data=json.dumps({'transactionTypes': ['SWAP']}),
            headers=headers,
            timeout=30
        )
        
        print(f'[HELIUS SETUP] Statut HTTP retourné: {response.status_code}')
        
        if response.status_code == 200:
            result = response.json()
            webhook_id = result.get('id', 'N/A')
            webhook_url = result.get('webhookUrl', 'N/A')
            
            print(f'[HELIUS SETUP] Webhook créé avec succès!')
            print(f'  ID du webhook: {webhook_id}')
            print(f'  URL du webhook: {webhook_url[:60]}...')
            
            return {
                'status': response.status_code,
                'webhook_id': webhook_id,
                'webhook_url': webhook_url,
                'message': 'Webhook Helius configuré avec succès'
            }
        else:
            error_msg = response.text if response.text else 'Aucun détail d'erreur'
            print(f'[HELIUS SETUP] Erreur: {error_msg}')
            return {'status': response.status_code, 'error': error_msg}
    
    except requests.exceptions.RequestException as e:
        print(f'[HELIUS SETUP] Erreur de connexion à Helius: {e}')
        return {'status': 0, 'error': str(e)}

def main():
    print('=' * 60)
    print('SETUP HELIUS WEBHOOK')
    print('=' * 60)
    
    api_key = input(f'API Key Helius: ').strip()
    if not api_key:
        print('[ERREUR] API Key vide. Abandon.')
        return
    
    cloudflare_url = input('URL publique Cloudflare [https://api.helius.xyz/v0/webhooks?api-key=]: ').strip()
    if not cloudflare_url:
        cloudflare_url = 'https://api.helius.xyz/v0/webhooks?api-key='
    
    result = create_helius_webhook(api_key, cloudflare_url)
    
    print('=' * 60)
    print('RAPPORT FINAL')
    print('=' * 60)
    
    if 'status' in result and result['status'] == 200:
        print(f'API Key Helius: {api_key}')
        print(f'ID du webhook créé: {result["webhook_id"]}')
        print(f'URL du webhook: {result["webhook_url"]["id"][:80]}...')
    else:
        print(f'Erreur de la création: {result.get("error", "Erreur inconnue")}')

if __name__ == '__main__':
    main()
