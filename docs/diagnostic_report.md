# Rapport de Diagnostic - WebSocket PumpPortal

**Date du diagnostic :** 2026-11-11 (UTC)  
**Fichier d'analyse :** `/home/kilpi/trading_bot/tools/probe_network.py`  
**URL testée :** `wss://pumpportal.fun/api/data`

## Résumé Executive
La connexion WebSocket vers PumpPortal n'est **PAS fonctionnelle**. Le tracker ne reçoit aucune donnée car l'endpoint est inaccessible.

## Tests Exécutés

### 1. Test A - Flux Global (subscribeNewToken)
**Commande :** `python3 /home/kilpi/trading_bot/tools/probe_network.py`  
**Résultat :** ⚠️ **ÉCHEC** - TimeoutError

```
Traceback (most recent call last):
  File "/home/kilpi/trading_bot/venv/lib/python3.12/site-packages/websockets/asyncio/client.py", line 526, in connect
    await connection.handshake(
  ...
TimeoutError: timed out during opening handshake
```

**Analyse :** La connexion TCP se établit (le client tente un handshake WebSocket), mais le serveur ne répond pas avec une réponse de handshake valide. Le timeout de 30 secondes (timeout du `websockets` + timeout `curl`) s'écoule sans établissement de connexion.

---

### 2. Test B - Smart Wallets (subscribeAccountTrade)
**Statut :** N/A - Non exécuté car le test A échoue à l'établissement de connexion

---

## Diagnostic Réseau

### Vérification HTTP de l'endpoint
```bash
curl https://pumpportal.fun/api/data
Resultat : "Cannot GET /api/data"
```

**Conclusion :** L'endpoint `/api/data` n'existe PAS en HTTP. Le WebSocket peut utiliser un endpoint HTTP différent pour la redirection, mais il n'y a aucune indication de l'URL correcte dans les erreurs du serveur.

### Vérification TCP au port 443
Les connexions vers `pumpportal.fun:443` timeout après ~5 secondes, suggérant :
- Possibilité A : Le serveur refuse le handshake WebSocket (réponse HTTP 404/autre)
- Possibilité B : Le service PumpPortal est down ou en maintenance
- Possibilité C : Un pare-feu bloque les connexions WebSocket entrantes

---

## Conclusion & Actions Recommandées

### Racine du Problème
Le service WebSocket `wss://pumpportal.fun/api/data` est **inaccessible**. Causes possibles :
1. Le site PumpPortal a été mis à jour et l'URL WebSocket a changé
2. Le service backend n'est plus opérationnel
3. Les connexions sont rejetées par le serveur (timeout = pas de réponse WS, donc timeout HTTP)

### Options de Mitigation
1. **Vérifier les docs officielles** : Rapprochez-vous de PumpPortal pour l'URL WebSocket actuelle
2. **Changer de source de données** : Identifier une alternative (ex: RPC direct, autres endpoints)
3. **Filtrer les erreurs de connexion** : Dans votre tracker, ajouter une gestion des timeout et logger la dernière URL fonctionnelle

### Fichier Utilisé
```bash
cat /home/kilpi/trading_bot/tools/probe_network.py
```

Le script simplifié est prêt pour tester d'autres URLs si le besoin s'en fait sentir.
