#!/usr/bin/env python3
"""
Helius Configuration Script
Fetches Cloudflare URL from Helius and updates webhook configuration.
"""

import json
import re
import time
import urllib.request
from pathlib import Path


def fetch_cloudflare_url():
    """Fetch the latest Cloudflare URL pattern from Helius logs."""
    # Read active positions for context
    active_file = Path("/home/kilpi/trading_bot/data/active_positions.json")
    if active_file.exists():
        with open(active_file) as f:
            data = json.load(f)
            positions = data.get("positions", {})
            
            if "Hero" in positions and "mint_address" in positions["Hero"]:
                print(f"Active Hero position mint: {positions['Hero']['mint_address']}")
    
    # Check Helius logs for Cloudflare URL updates
    log_file = Path("/home/kilpi/trading_bot/logs/helius_listener.log")
    if not log_file.exists():
        print("⚠️  Helius logs not found at /home/kilpi/trading_bot/logs/helius_listener.log")
        return None
    
    content = log_file.read_text()
    
    # Look for Cloudflare IP patterns in recent logs
    cloudflare_ips = re.findall(r'Cloudflare|23\.?(\d{1,3}\.){3}\d{1,3}|(?:45\.?(\d{1,3}\.){3}\d{1,3})', content)
    
    if not cloudflare_ips:
        print("⚠️  No Cloudflare patterns found in logs")
        return None
    
    # Extract last few Cloudflare-like IPs
    potential_urls = [ip for ip in cloudflare_ips if len(ip[0]) == 24]  # IPv4 pattern
    if potential_urls:
        print(f"Potential Cloudflare URL candidates from logs: {potential_urls[-3:]}")
    
    return None


def update_helius_config(cloudflare_url):
    """Update Helius webhook configuration with new Cloudflare URL."""
    if not cloudflare_url:
        print("❌ No valid Cloudflare URL found to update")
        return False
    
    try:
        # Standard Helius API endpoint for webhooks (using REST API)
        api_endpoint = "https://api.helius.xyz/v0/webhooks"
        
        # Prepare authorization - would typically use API key from env/config
        headers = {
            "Content-Type": "application/json",
            # "Authorization": f"Bearer {API_KEY}",  # Would need API key
        }
        
        payload = {
            "callbackUrl": cloudflare_url,
            "isActive": True,
            "events": ["account-activity-by-account-addresses"],
            "addressFilters": ["*"]  # Subscribe to all addresses for now
        }
        
        # Try PUT request to update existing webhook
        req = urllib.request.Request(
            api_endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="PUT"
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                print(f"✅ Helius webhook updated successfully!")
                print(f"   Response: {json.dumps(result, indent=2)[:500]}")
                return True
                
        except urllib.error.HTTPError as e:
            error_msg = json.loads(e.read().decode()).get("error", str(e))
            print(f"❌ Webhook update failed: {error_msg}")
            
            # Fallback: Try POST to create new webhook if PUT fails (409 Conflict)
            if "409" in str(e.code):
                print("   Trying POST to create new webhook...")
                req.method = "POST"
                try:
                    with urllib.request.urlopen(req) as response:
                        result = json.loads(response.read().decode())
                        print(f"✅ New Helius webhook created!")
                        return True
                except Exception as post_err:
                    print(f"   POST also failed: {post_err}")
            
            return False
            
    except Exception as e:
        print(f"❌ Error updating Helius config: {e}")
        return False


def main():
    """Main execution flow."""
    print("=" * 60)
    print("🔧 HELIUS CONFIGURATION UPDATER")
    print("=" * 60)
    
    # Fetch Cloudflare URL from logs
    cloudflare_url = fetch_cloudflare_url()
    
    if not cloudflare_url:
        print("\n⚠️  No valid Cloudflare URL found.")
        print("💡 Skipping Helius config update - check logs for available URLs.")
        return
    
    # Attempt to update configuration
    success = update_helius_config(cloudflare_url)
    
    if success:
        print("\n✅ HELIUS CONFIG UPDATED SUCCESSFULLY!")
        
        # Save updated config to file for verification
        config_path = Path("/home/kilpi/trading_bot/data/helius_config.json")
        with open(config_path, "w") as f:
            json.dump({
                "cloudflare_url": cloudflare_url,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }, f, indent=2)
        
        print(f"   Config saved to: {config_path}")
    else:
        print("\n⚠️  Helius config update skipped or failed.")


if __name__ == "__main__":
    main()
