import argparse
import json
import asyncio
from datetime import datetime
from collections import defaultdict
import websockets
import requests

# WebSocket配置（更新支持更多交易所）
EXCHANGE_WS_CONFIG = {
    'binance': {
        'url': 'wss://stream.binance.com:9443/ws/{symbol}@trade',
        'price_key': 'p',
        'symbol_format': lambda s: s.replace('/', '').lower()
    },
    'okx': {
        'url': 'wss://ws.okx.com:8443/ws/v5/public',
        'price_key': 'lastPx',
        'subscribe_msg': {
            "op": "subscribe",
            "args": [{"channel": "trades", "instId": "{symbol}"}]
        },
        'symbol_format': lambda s: s.replace('/', '-')
    },
    'bitget': {
        'url': 'wss://ws.bitget.com/spot/v1/stream',
        'price_key': 'price',
        'subscribe_msg': {
            "op": "subscribe",
            "args": [{
                "instType": "SP",
                "channel": "trade",
                "instId": "{symbol}"
            }]
        },
        'symbol_format': lambda s: s.replace('/', '')
    },
    'htx': {
        'url': 'wss://api-aws.huobi.pro/ws',
        'price_key': 'price',
        'symbol_format': lambda s: s.replace('/', '').lower() + '.trade.detail'
    }
}

class SinglePairMonitor:
    def __init__(self, symbol, exchanges, threshold, webhook_url):
        self.symbol = symbol
        self.exchanges = exchanges
        self.threshold = threshold
        self.webhook_url = webhook_url
        
        # 价格存储结构：{exchange: price}
        self.prices = defaultdict(lambda: None)
        self.lock = asyncio.Lock()
        self.last_alert_time = defaultdict(lambda: 0)

    async def send_alert(self, spread, prices):
        """发送价差警报（带频率限制）"""
        now = time.time()
        if now - self.last_alert_time[self.symbol] < 60:  # 1分钟间隔
            return
            
        alert_msg = (
            f"🚨 价差警报！{self.symbol}\n"
            f"当前价差: {spread:.2f}% (阈值: {self.threshold}%)\n"
            "交易所价格:\n" + 
            "\n".join([f"{ex.upper()}: {price}" for ex, price in prices.items()])
        )
        try:
            await asyncio.to_thread(
                requests.post,
                self.webhook_url,
                json={"msgtype": "text", "text": {"content": alert_msg}}
            )
            self.last_alert_time[self.symbol] = now
            print(f"警报已发送：{self.symbol}")
        except Exception as e:
            print(f"警报发送失败：{str(e)}")

    async def handle_price_update(self, exchange, price):
        """处理价格更新并立即计算价差"""
        async with self.lock:
            # 更新价格
            self.prices[exchange] = float(price)
            
            # 过滤无效价格
            valid_prices = {k: v for k, v in self.prices.items() if v is not None}
            if len(valid_prices) < 2:
                return

            # 计算价差
            min_price = min(valid_prices.values())
            max_price = max(valid_prices.values())
            spread = ((max_price - min_price) / min_price) * 100

            # 打印实时状态
            status = [
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {self.symbol}",
                *[f"{ex.upper()}: {price:.4f}" for ex, price in valid_prices.items()],
                f"价差: {spread:.4f}%"
            ]
            print("\n".join(status) + "\n" + "-"*40)

            # 触发警报
            if spread >= self.threshold:
                await self.send_alert(spread, valid_prices)

    async def connect_exchange(self, exchange):
        """连接交易所WebSocket"""
        config = EXCHANGE_WS_CONFIG.get(exchange)
        if not config:
            print(f"Unsupported exchange: {exchange}")
            return

        formatted_symbol = config['symbol_format'](self.symbol)
        
        while True:
            try:
                if exchange == 'htx':
                    # HTX需要特殊处理订阅消息
                    async with websockets.connect(config['url']) as ws:
                        sub_msg = json.dumps({
                            "sub": f"market.{formatted_symbol}",
                            "id": "price_monitor"
                        })
                        await ws.send(sub_msg)
                        
                        async for msg in ws:
                            data = json.loads(msg)
                            if 'ping' in data:
                                # 保持连接心跳
                                pong_msg = json.dumps({"pong": data['ping']})
                                await ws.send(pong_msg)
                            elif 'tick' in data:
                                price = data['tick']['data'][0]['price']
                                await self.handle_price_update(exchange, price)
                
                elif exchange == 'bitget':
                    async with websockets.connect(config['url']) as ws:
                        sub_msg = json.dumps(
                            config['subscribe_msg']
                        ).replace("{symbol}", formatted_symbol)
                        await ws.send(sub_msg)
                        
                        async for msg in ws:
                            data = json.loads(msg)
                            # 添加更精确的消息格式验证
                            if data.get('action') in ['snapshot', 'update']:
                                # 确保data字段是有效列表格式
                                trades = data.get('data', [])
                                if isinstance(trades, list) and len(trades) > 0:
                                    latest_trade = trades[0]  # 总取最新成交
                                    if config['price_key'] in latest_trade:
                                        price = latest_trade[config['price_key']]
                                        await self.handle_price_update(exchange, price)
                
                else:  # 处理其他交易所
                    url = config['url'].format(symbol=formatted_symbol)
                    if exchange == 'okx':
                        url = config['url']
                    
                    async with websockets.connect(url) as ws:
                        if 'subscribe_msg' in config:
                            sub_msg = json.dumps(
                                config['subscribe_msg']
                            ).replace("{symbol}", formatted_symbol)
                            await ws.send(sub_msg)
                        
                        async for msg in ws:
                            data = json.loads(msg)
                            if exchange == 'okx' and 'data' in data:
                                price = data['data'][0][config['price_key']]
                            elif exchange == 'binance':
                                price = data[config['price_key']]
                            else:
                                continue
                            await self.handle_price_update(exchange, price)
                            
            except Exception as e:
                print(f"{exchange}连接错误：{str(e)}，5秒后重连...")
                await asyncio.sleep(5)

async def main():
    parser = argparse.ArgumentParser(description="单交易对多交易所实时价差监控")
    parser.add_argument('--symbol', required=True, help="监控的交易对，例如: BTC/USDT")
    parser.add_argument('--exchanges', required=True, nargs='+', 
                       choices=['binance', 'okx', 'bitget', 'htx'], 
                       help="监控的交易所列表")
    parser.add_argument('--threshold', type=float, default=0.1,
                       help="触发警报的价差百分比 (默认: 0.1)")
    parser.add_argument('--webhook', required=True,
                       help="报警通知的Webhook URL")
    
    args = parser.parse_args()

    print("\n" + "="*40)
    print(f"启动单交易对监控系统")
    print(f"交易对: {args.symbol}")
    print(f"交易所: {', '.join(args.exchanges)}")
    print(f"警报阈值: {args.threshold}%")
    print("="*40 + "\n")

    monitor = SinglePairMonitor(
        symbol=args.symbol,
        exchanges=args.exchanges,
        threshold=args.threshold,
        webhook_url=args.webhook
    )

    # 启动所有交易所连接
    tasks = [monitor.connect_exchange(ex) for ex in args.exchanges]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n监控已停止")