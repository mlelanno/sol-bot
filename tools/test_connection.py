import asyncio
import aiohttp
import json

async def test():
    uri = "wss://pumpportal.fun/api/data"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("⏳ Tentative de connexion WebSocket à PumpPortal...")
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.ws_connect(uri, timeout=aiohttp.ClientWSTimeout(ws_close=10)) as ws:
                print(" Handshake réussi ! Envoi de subscribeNewToken...")
                await ws.send_str(json.dumps({"method": "subscribeNewToken"}))
                
                print(" En attente du premier token créé sur Pump.fun...")
                msg = await asyncio.wait_for(ws.receive(), timeout=10)
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    print(f" ÉVÉNEMENT CAPTURÉ EN DIRECT :\n{msg.data[:200]}...")
                else:
                    print(f"Message reçu (type {msg.type}): {msg.data}")
    except asyncio.TimeoutError:
        print("❌ Timeout : le serveur n'a renvoyé aucun token en 10s.")
    except Exception as e:
        print(f"❌ Échec de connexion : {type(e).__name__} -> {e}")

if __name__ == "__main__":
    asyncio.run(test())
