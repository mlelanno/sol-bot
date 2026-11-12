#!/usr/bin/env python3
"""Extrait l'URL du tunnel Cloudflare depuis les logs."""
import re
from pathlib import Path

def extract_cloudflare_url():
    log_path = Path('/home/kilpi/trading_bot/logs/cloudflared.log')
    try:
        content = log_path.read_text(errors='ignore')
        pattern = r'https://[a-zA-Z0-9_-]+\.(?:try)?cloudflare\.com'
        matches = re.findall(pattern, content)
        if matches:
            print(f"✓ URL Cloudflare trouvée : {matches[0]}")
            return matches[0]
        print("⚠ Pas d'URL trycloudflare.com dans les logs")
    except Exception as e:
        print(f"Erreur lecture logs : {e}")
    return None

if __name__ == '__main__':
    main = extract_cloudflare_url()
