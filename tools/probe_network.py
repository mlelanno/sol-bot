#!/usr/bin/env python3
import asyncio, json, time

WEBSOCKET_URL = "wss://pumpportal.fun/api/data"

async def t_a():
    print("=== TEST A : FLUX GLOBAL ===")
    s = time.time()
    async with __import__("websockets").connect(WEBSOCKET_URL) as ws:
        await ws.send(json.dumps({"method": "subscribeNewToken"}))
        while time.time()-s<10:
            try:
                msg=await asyncio.wait_for(ws.recv(), timeout=0.5)
                d=json.loads(msg)
                print(f"  {d.get('txType','??')}")
            except: pass
    return "OK"

async def t_b():
    print("=== TEST B : SMART WALLETS ===")
    s = time.time()
    with open('/home/kilpi/trading_bot/data/smart_wallets.json') as f:
        wallets=json.load(f)
    addrs=[w.get('address','') for w in (list(wallets.values()) if isinstance(wallets,dict) else wallets)[:50]]
    print(f'Loaded {len(addrs)} addresses')
    async with __import__("websockets").connect(WEBSOCKET_URL) as ws:
        await ws.send(json.dumps({'method': 'subscribeAccountTrade', 'keys': addrs}))
        while time.time()-s<15:
            try:
                msg=await asyncio.wait_for(ws.recv(), timeout=0.5)
                raw=json.loads(msg)
                print(f"  txType={raw.get('txType','??')} mint={raw.get('mint','')[:8]}...{raw.get('mint','')[-4:]} from={raw.get('accountPubkey','')[0:10]}")
            except Exception as e:
                print(f"  ERROR: {e}")
    return "OK"

async def main():
    await t_a()
    await t_b()

if __name__=='__main__':
    asyncio.run(main())