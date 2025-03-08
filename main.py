import asyncio
import websockets
import json
import yaml
import argparse
import time
import requests
import ccxt
from typing import Dict, Any

class PriceManager:
    def __init__(self, exchanges: list):
        self.prices: Dict[str, float] = {ex: None for ex in exchanges}

    def update_price(self, exchange: str, price: float):
        self.prices[exchange] = price

    def get_prices(self) -> Dict[str, float]:
        return self.prices.copy()

def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_exchange_instance(exchange_name: str, config: Dict) -> ccxt.Exchange:
    conf = config['exchanges'][exchange_name]
    cls = getattr(ccxt, exchange_name)
    return cls({
        'apiKey': conf['apiKey'],
        'secret': conf['secret'],
        'enableRateLimit': True,
    })

async def binance_ws(symbol: str, price_manager: PriceManager):
    symbol_ws = symbol.lower().replace('/', '')
    url = f"wss://stream.binance.com:9443/ws/{symbol_ws}@ticker"
    async with websockets.connect(url) as ws:
        while True:
            try:
                data = await ws.recv()
                ticker = json.loads(data)
                price = float(ticker['c'])
                price_manager.update_price('binance', price)
            except Exception as e:
                print(f"Binance WS error: {e}")
                await asyncio.sleep(5)

async def okx_ws(symbol: str, price_manager: PriceManager):
    symbol_ws = symbol.replace('/', '-')
    url = "wss://ws.okx.com:8443/ws/v5/public"
    async with websockets.connect(url) as ws:
        sub_msg = json.dumps({
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": symbol_ws}]
        })
        await ws.send(sub_msg)
        while True:
            try:
                data = await ws.recv()
                msg = json.loads(data)
                if 'data' in msg and msg['arg']['channel'] == 'tickers':
                    price = float(msg['data'][0]['last'])
                    price_manager.update_price('okx', price)
            except Exception as e:
                print(f"OKX WS error: {e}")
                await asyncio.sleep(5)

async def bitget_ws(symbol: str, price_manager: PriceManager):
    symbol_ws = symbol.replace('/', '')
    url = f"wss://ws.bitget.com/spot/v1/stream"
    async with websockets.connect(url) as ws:
        sub_msg = json.dumps({
            "op": "subscribe",
            "args": [{"instType": "SP", "channel": "ticker", "instId": symbol_ws}]
        })
        await ws.send(sub_msg)
        while True:
            try:
                data = await ws.recv()
                msg = json.loads(data)
                if 'data' in msg:
                    price = float(msg['data'][0]['last'])
                    price_manager.update_price('bitget', price)
            except Exception as e:
                print(f"Bitget WS error: {e}")
                await asyncio.sleep(5)

def send_webhook(webhook_url: str, message: str):
    data = {
        "msgtype": "text",
        "text": {
            "content": message
        }
    }
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Webhook发送失败: {e}")

def execute_trade(config: Dict, exchange_name: str, symbol: str, side: str, amount: float):
    ex = get_exchange_instance(exchange_name, config)
    try:
        order = ex.create_market_order(symbol, side, amount)
        while True:
            order_info = ex.fetch_order(order['id'], symbol)
            if order_info['status'] == 'closed':
                return order_info
            time.sleep(1)
    except Exception as e:
        print(f"{exchange_name}交易失败: {e}")
        return None

def calculate_profit(config: Dict, buy_ex: str, sell_ex: str, buy_price: float, sell_price: float, amount: float) -> float:
    buy_fee = config['exchanges'][buy_ex]['fee']
    sell_fee = config['exchanges'][sell_ex]['fee']
    gas_fee = config['exchanges'][buy_ex].get('gas', 0)
    
    cost = amount * buy_price * (1 + buy_fee)
    revenue = amount * sell_price * (1 - sell_fee)
    return revenue - cost - gas_fee

async def monitor(price_manager: PriceManager, config: Dict, args):
    while True:
        prices = price_manager.get_prices()
        if all(prices[ex] is not None and prices[ex] > 0 for ex in args.exchanges):
            sorted_ex = sorted(args.exchanges, key=lambda x: prices[x])
            lowest_ex = sorted_ex[0]
            highest_ex = sorted_ex[-1]
            spread = prices[highest_ex] - prices[lowest_ex]

            if spread >= args.threshold:
                symbol_base = args.symbol.split('/')[1]
                buy_ex = get_exchange_instance(lowest_ex, config)
                balance = buy_ex.fetch_balance()[symbol_base]['free']
                
                if balance <= 0:
                    print(f"{lowest_ex} 余额不足")
                    continue
                
                amount = balance / prices[lowest_ex]
                loop = asyncio.get_event_loop()
                buy_order = await loop.run_in_executor(
                    None, execute_trade, config, lowest_ex, args.symbol, 'buy', amount
                )
                if buy_order is None:
                    continue

                sell_amount = buy_order['filled'] - config['exchanges'][lowest_ex].get('gas', 0)
                if sell_amount <= 0:
                    print("有效数量不足")
                    continue

                sell_order = await loop.run_in_executor(
                    None, execute_trade, config, highest_ex, args.symbol, 'sell', sell_amount
                )
                if sell_order is None:
                    continue

                profit = calculate_profit(
                    config, lowest_ex, highest_ex,
                    buy_order['price'], sell_order['price'],
                    buy_order['filled']
                )
                msg = (f"套利完成\n"
                       f"买入: {lowest_ex} {buy_order['filled']}@{buy_order['price']}\n"
                       f"卖出: {highest_ex} {sell_order['filled']}@{sell_order['price']}\n"
                       f"利润: {profit:.4f} {symbol_base}")
                send_webhook(args.webhook, msg)
        await asyncio.sleep(1)

async def main(args, config):
    price_manager = PriceManager(args.exchanges)
    ws_tasks = []
    
    if 'binance' in args.exchanges:
        ws_tasks.append(asyncio.create_task(binance_ws(args.symbol, price_manager)))
    if 'okx' in args.exchanges:
        ws_tasks.append(asyncio.create_task(okx_ws(args.symbol, price_manager)))
    if 'bitget' in args.exchanges:
        ws_tasks.append(asyncio.create_task(bitget_ws(args.symbol, price_manager)))
    
    monitor_task = asyncio.create_task(monitor(price_manager, config, args)))
    
    await asyncio.gather(*ws_tasks, monitor_task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True, help='交易对，例如BTC/USDT')
    parser.add_argument('--exchanges', nargs='+', required=True, 
                       choices=['binance', 'okx', 'bitget'], help='交易所列表')
    parser.add_argument('--webhook', required=True, help='企业微信Webhook URL')
    parser.add_argument('--threshold', type=float, required=True,
                       help='触发套利的最小价差阈值')
    args = parser.parse_args()

    config = load_config('config.yaml')
    
    try:
        asyncio.run(main(args, config))
    except KeyboardInterrupt:
        print("程序已终止")