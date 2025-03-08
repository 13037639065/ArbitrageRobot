import websockets
import asyncio
import json

async def listen_price():
    async with websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@trade")  as ws:
        while True:
            data = await ws.recv() 
            price = json.loads(data)['p'] 
            print(f"BTC实时价格: {price}")

asyncio.get_event_loop().run_until_complete(listen_price()) 