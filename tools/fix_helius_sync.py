#!/usr/bin/env python3
"""Script de réparation de la synchronisation Helius."""
import os
import json
import re
import requests
import time


def _print_create_error(response, payload):
    """Afficher les détails d'erreur lors de la création échouée."""
    if response.status_code in [500, 503]:
        print(f"\n  ✗ Erreur serveur temporaire ({response.status_code})")
        print(f"    Message: {response.text[:200]}")
    else:
        print(f"\n  ✗ Échec après {response.status_code}: {response.text[:100] if response.text else 'No text'}")
        try:
            error_data = response.json()
            for key, value in error_data.items():
                if isinstance(value, (list, dict)):
                    print(f"    {key}: {value[:500]}..." if len(str(value)) > 500 else f"    {key}: {value}")
                else:
                    print(f"    {key}: {value}")
        except:
            pass

# 1. Lire HELIUS_API_KEY depuis le fichier .env
with open('/home/kilpi/trading_bot/.env', 'r') as f:
    for line in f:
        if line.startswith('HELIUS_API_KEY='):
            helius_api_key = line.split('=')[1].strip()
            break

# 2. Lire le log cloudflared et extraire la dernière URL publique active
with open('/home/kilpi/trading_bot/logs/cloudflared.log', 'r') as f:
    log_content = f.read()

# Extraire toutes les URLs trycloudflare.com et prendre la dernière
urls_match = re.findall(r'https://([a-z0-9-]+\.trycloudflare\.com)', log_content)
if urls_match:
    tunnel_url = urls_match[-1]
else:
    # Fallback : recherche plus simple pour "Visit it at"
    match = re.search(r' Visit it at \(it may take some time to be reachable\): (\S+)', log_content)
    if match:
        tunnel_url = match.group(1)
    else:
        raise ValueError("Aucune URL trycloudflare.com trouvée dans le log")

print(f"✓ Tunnel URL détectée : {tunnel_url}")

# 3. Charger toutes les adresses depuis smart_wallets.json
with open('/home/kilpi/trading_bot/data/smart_wallets.json', 'r') as f:
    addresses = json.load(f)

addresses_count = len(addresses)
print(f"✓ Chargement de {addresses_count} adresses depuis smart_wallets.json")

# 4. Interroger Helius API pour l'état AVANT correction
helius_webhooks_url = "https://api.helius.xyz/v0/webhooks?api-key=" + helius_api_key
response_before = requests.get(helius_webhooks_url)
if response_before.status_code == 200:
    webhooks_data = response_before.json()
    
    if len(webhooks_data) == 0:
        print("Aucun webhook trouvé, création d'un nouveau.")
    else:
        active_webhook_list = [w for w in webhooks_data if w.get('active', False)]
        secondary_webhooks = [w for w in webhooks_data if not w.get('active', False)]
        
        # Afficher l'état AVANT correction
        webhookID = None
        webhookURL = None
        
        if active_webhook_list:
            w = active_webhook_list[0]
            webhookID = w['webhookID']
            webhookURL = w['webhookURL']
            
            # Récupérer les détails complets du webhook actif (avec accountAddresses)
            details_url = "https://api.helius.xyz/v0/webhooks/" + webhookID + "?api-key=" + helius_api_key
            response_details_init = requests.get(details_url)
            if response_details_init.status_code == 200:
                webhook_full_init = response_details_init.json()
                len_account_addresses_init = len(webhook_full_init.get('accountAddresses', []))
        
        print(f"=== ÉTAT AVANT CORRECTION ===")
        print(f"  webhooks_total: {len(webhooks_data)}")
        print(f"  active_webhook: {webhookID if webhookID else 'N/A'}")
        print(f"  webhookURL: {webhookURL}")
        print(f"  len(accountAddresses): {len_account_addresses_init if 'len_account_addresses_init' in locals() else 'N/A'}")
        
        # Afficher le nombre de webhooks secondaires qui seront supprimés
        secondary_count = sum(1 for w in webhooks_data if not w.get('active', True))
        print(f"  webhooks_secondaires: {secondary_count}")

# 5. Supprimer tout webhook secondaire s'il y en a plus d'un
if response_before.status_code == 200:
    for w in webhooks_data:
        if not w.get('active', True) and 'webhookID' in w:
            delete_url = "https://api.helius.xyz/v0/webhooks/" + w['webhookID'] + "?api-key=" + helius_api_key
            print(f"  Suppression du webhook secondaire {w['webhookID']}...")
            requests.delete(delete_url)

# Mettre à jour le webhook principal (ou créer si n'existe pas)
if response_before.status_code == 200:
    active_webhook_list = [w for w in webhooks_data if w.get('active', False)]
    
    if not active_webhook_list:
        # Création d'un nouveau webhook principal via POST
        payload = {
            "webhookURL": tunnel_url + "/webhook",
            "transactionTypes": ["SWAP"],
            "accountAddresses": addresses,
            "webhookType": "enhanced"
        }
        print(f"\\nCréation d'un nouveau webhook principal...")
        
        # Gestion des retries pour les erreurs serveur temporaires (500, 503)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response_create = requests.post(helius_webhooks_url, json=payload, timeout=15)
                print(f"  Création (tentative {attempt + 1}/{max_retries}): {response_create.status_code}")
                
                if response_create.status_code in [201, 200]:
                    new_webhook_data = response_create.json()
                    webhookID = new_webhook_data.get('webhookID')
                    webhookURL = payload['webhookURL']
                    print(f"  ✓ Webhook créé avec succès!")
                    
                elif response_create.status_code in [500, 503]:
                    # Erreur serveur temporaire - retry avec backoff
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # 2s, 4s, 8s
                        print(f"\\n  ⚠️ Erreur serveur ({response_create.status_code}): Helius temporairement indisponible")
                        print(f"    Retry dans {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        # Dernier retry échoué, lancer le debug
                        _print_create_error(response_create, payload)
                        
                elif response_create.status_code in [400, 401, 422]:
                    # Erreur de notre côté - afficher et relancer avec assertion
                    _print_create_error(response_create, payload)
                    
                else:
                    # Autres codes d'erreur non gérés
                    print(f"\\n  Erreur inattendue ({response_create.status_code}): {response_create.text[:200]}")
                    raise AssertionError(f"API Helius retourné statut {response_create.status_code}: {response_create.text[:300]}")
                    
            except Exception as e:
                print(f"\\n  ⚠️ Exception lors de la tentative {attempt + 1}: {str(e)[:200]}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    print(f"    Retry dans {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
                    
        else:
            # Tous les retries ont échoué
            _print_create_error(response_create, payload)
            raise AssertionError("API Helius a rejeté la création du webhook après plusieurs tentatives.")

    else:
        # Mise à jour du webhook principal actif via PUT
        w = active_webhook_list[0]
        put_url = "https://api.helius.xyz/v0/webhooks/" + w['webhookID'] + "?api-key=" + helius_api_key
        
        print(f"  Payload pour la mise à jour (nombre d'adresses: {len(addresses)}):")
        payload_update = {
            "webhookURL": tunnel_url + "/webhook",
            "transactionTypes": ["SWAP"],
            "accountAddresses": addresses,
            "webhookType": "enhanced"
        }
        print(f"    webhookURL: {payload_update['webhookURL']}")
        print(f"    transactionTypes: {payload_update['transactionTypes']}")
        print(f"    accountAddresses count: {len(payload_update['accountAddresses'])}")
        print(f"    webhookType: {payload_update['webhookType']}")
        
        response_put = requests.put(put_url, json=payload_update)
        print(f"\nMise à jour du webhook principal...")
        print(f"  HTTP status: {response_put.status_code}")
        
        if response_put.status_code in [200, 201]:
            try:
                update_response = response_put.json()
                print(f"  Réponse du serveur (statut {response_put.status_code}):")
                for key, value in update_response.items():
                    if key != '_links':  # Ignorer les métadonnées
                        print(f"    {key}: {value}")
            except:
                print(f"  Contenu de la réponse: {response_put.text[:200]}...")
        else:
            print(f"\n  Erreur lors de la mise à jour (status {response_put.status_code}):")
            try:
                error_response = response_put.json()
                error_msg = error_response.get('error', 'Erreur inconnue')
                if isinstance(error_msg, dict):
                    error_msg = str(error_msg)
                print(f"    Détail de l'erreur: {error_msg[:500]}")
            except:
                print(f"    Message brut: {response_put.text[:200]}")
            
            # Si la mise à jour échoue avec un statut 500, c'est probablement le webhook existant qui est corrompu
            # On supprime ce webhook et on en crée un nouveau
            if response_put.status_code == 500:
                print(f"\n  Tentative de suppression du webhook existant corrompu (webhookID: {webhookID})...")
                delete_url = "https://api.helius.xyz/v0/webhooks/" + webhookID + "?api-key=" + helius_api_key
                response_delete = requests.delete(delete_url)
                print(f"  Suppression du webhook existant: status {response_delete.status_code}")
                try:
                    delete_response = response_delete.json()
                    print(f"    Réponse de suppression: {delete_response}")
                except:
                    print(f"    Message brut de suppression: {response_delete.text[:200]}")
            
            # Recréer le webhook avec toutes les adresses
            print(f"\n  Création d'un nouveau webhook principal...")
            payload = {
                "webhookURL": tunnel_url + "/webhook",
                "transactionTypes": ["SWAP"],
                "accountAddresses": addresses,
                "webhookType": "enhanced"
            }
            print(f"    Payload pour la création (nombre d'adresses: {len(addresses)}):")
            print(f"      webhookURL: {payload['webhookURL']}")
            print(f"      transactionTypes: {payload['transactionTypes']}")
            print(f"      accountAddresses count: {len(payload['accountAddresses'])}")
            print(f"      webhookType: {payload['webhookType']}")
            
            # Retry logic pour les erreurs 500 temporaires
            max_retries = 3
            retry_delays = [2, 4, 8]  # Secondes pour backoff exponentiel
            
            last_error = None
            for attempt in range(max_retries + 1):
                response_create = requests.post(helius_webhooks_url, json=payload)
                print(f"  Création (tentative {attempt+1}/{max_retries}): HTTP {response_create.status_code}")
                
                if response_create.status_code in [201, 200]:
                    new_webhook_data = response_create.json()
                    webhookID = new_webhook_data.get('webhookID')
                    webhookURL = payload['webhookURL']
                    break  # Succès
                    
                elif response_create.status_code == 500:
                    error_json = None
                    try:
                        create_error = response_create.json()
                        error_json = str(create_error)[:200]
                    except:
                        pass
                    
                    last_error = f"Erreur 500 - {error_json or 'Détails non disponibles'}"
                    print(f"\n    Erreur 500 (tentative {attempt+1}/{max_retries}): {last_error}")
                    
                    if attempt < max_retries:
                        delay = retry_delays[attempt]
                        print(f"    Retentative dans {delay} secondes...")
                        time.sleep(delay)
                    else:
                        raise AssertionError(
                            f"API Helius a rejeté la création du webhook avec statut 500 après {max_retries} tentatives.\n"
                            f"Dernière erreur: {last_error}\n"
                            f"Payload envoyé:\n"
                            f"  - webhookURL: {payload['webhookURL'][:100]}...\n"
                            f"  - transactionTypes: {payload.get('transactionTypes')}\n"
                            f"  - accountAddresses count: {len(payload.get('accountAddresses', []))}"
                        )
                else:
                    # Autres erreurs (4xx, autres 5xx)
                    print(f"\n  Erreur inattendue lors de la création (status {response_create.status_code}):")
                    print(f"    Contenu brut: {response_create.text[:500]}")
                    
                    if attempt == max_retries:
                        raise AssertionError(
                            f"API Helius a rejeté la création du webhook avec statut {response_create.status_code}: {response_create.text[:300]}"
                        )

# Refaire un GET pour l'état APRÈS correction
print("\n=== VÉRIFICATION POST-CORRECTION ===")
response_after = requests.get(helius_webhooks_url)

if response_after.status_code != 200:
    print(f"\nErreur lors de la réponse GET après correction (status {response_after.status_code}):")
    try:
        error_msg = response_after.json()
        print(f"  Message d'erreur API Helius: {error_msg}")
    except:
        print(f"  Contenu brut: {response_after.text[:500]}")
    raise AssertionError(f"API Helius a retourné un statut {response_after.status_code} lors de la vérification.")

webhooks_after = response_after.json()

active_webhooks_after = [w for w in webhooks_after if w.get('active', False)]
if active_webhooks_after:
    webhook_after = active_webhooks_after[0]
    
    # Récupérer les détails complets du webhook (avec accountAddresses)
    details_url = "https://api.helius.xyz/v0/webhooks/" + webhook_after['webhookID'] + "?api-key=" + helius_api_key
    response_details = requests.get(details_url)
    if response_details.status_code == 200:
        webhook_full = response_details.json()
        addresses_in_webhook = len(webhook_full.get('accountAddresses', []))
        
        assert addresses_in_webhook == addresses_count, \
            f"Assertion échouée: expected {addresses_count} adresses, got {addresses_in_webhook}"
        assert webhook_after['webhookURL'] == tunnel_url + "/webhook", \
            f"Assertion échouée: URL attendue '{tunnel_url}/webhook', got '{webhook_full.get('webhookURL', 'N/A')}'"
        
        print(f"  ✓ Compteur d'adresses actives = {addresses_in_webhook} (attendu: {addresses_count})")
        print(f"  ✓ webhookURL = {webhook_full.get('webhookURL', 'N/A')} (attendu: {tunnel_url}/webhook)")
        print(f"\n=== SYNCHRONISATION HELIUS RÉUSSIE ===")
    else:
        # Fallback si on ne peut pas récupérer les détails
        assert len(webhook_after.get('accountAddresses', [])) == addresses_count, \
            f"Assertion échouée: expected {addresses_count} adresses, got {len(webhook_after.get('accountAddresses', []))}"
        assert webhook_after['webhookURL'] == tunnel_url + "/webhook", \
            f"Assertion échouée: URL attendue '{tunnel_url}/webhook', got '{webhook_after['webhookURL']}'"
        print(f"  ✓ Compteur d'adresses actives = {len(webhook_after.get('accountAddresses', []))} (attendu: {addresses_count})")
        print(f"  ✓ webhookURL = {webhook_after['webhookURL']} (attendu: {tunnel_url}/webhook)")
        print(f"\n=== SYNCHRONISATION HELIUS RÉUSSIE ===")
else:
    raise AssertionError("Aucun webhook actif après la correction.")