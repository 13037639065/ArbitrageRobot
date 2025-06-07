import argparse 
import asyncio 
import websockets 
import ccxt 
import json 
from decimal import Decimal, ROUND_DOWN 
 
# 全局变量存储交易状态 
position = {
    'opened': False,
    'entry_price': None,
    'highest_price': None,
    'trailing_stop_triggered': False 
}
 
async def monitor_price(args, exchange):
    uri = f"wss://fstream.binance.com/ws/{args.symbol.lower()}@markPrice" 
    
    async with websockets.connect(uri)  as websocket:
        while True:
            try:
                message = await websocket.recv() 
                data = json.loads(message) 
                current_price = Decimal(data['p'])
                
                # 首次初始化最高价 
                if position['highest_price'] is None:
                    position['highest_price'] = current_price 
                
                await check_trading_conditions(current_price, args, exchange)
 
            except Exception as e:
                print(f"WebSocket error: {str(e)}")
                break 
 
async def check_trading_conditions(price, args, exchange):
    # 横盘检测（过去10个价格波动小于1%）
    if len(price_history) >= 10:
        max_price = max(price_history)
        min_price = min(price_history)
        if (max_price - min_price)/min_price < Decimal('0.01'):
            print("横盘条件触发，平仓！")
            await close_position(args, exchange)
            return 
    
    # 开仓逻辑 
    if not position['opened']:
        base_price = price  # 实际应替换为EMA或其他基准价 
        change_threshold = base_price * args.threshold  / Decimal(100)
        
        if abs(price - base_price) >= change_threshold:
            side = 'buy' if price > base_price else 'sell'
            await open_position(price, side, args, exchange)
    
    # 持仓后逻辑 
    else:
        # 更新最高价 
        position['highest_price'] = max(position['highest_price'], price)
        
        # 固定止损 
        stop_loss_price = position['entry_price'] * (1 - args.stop_loss/100) 
        if price <= stop_loss_price:
            print(f"触发固定止损@{stop_loss_price}")
            await close_position(args, exchange)
        
        # 回撤止损 
        drawdown = (position['highest_price'] - price)/position['highest_price']
        if drawdown >= args.trailing_stop/100: 
            print(f"触发回撤止损@{price}")
            await close_position(args, exchange)
 
async def open_position(price, side, args, exchange: ccxt.Exchange):
    try:
        order = exchange.create_order( 
            symbol=args.symbol, 
            type='market',
            side=side,
            amount=exchange.amount_to_precision(args.symbol,  args.quantity), 
            params={'positionSide': 'LONG' if side == 'buy' else 'SHORT'}
        )
        position.update({ 
            'opened': True,
            'entry_price': price,
            'highest_price': price 
        })
        print(f"开仓成功！方向：{side} 价格：{price}")
        
    except ccxt.BaseError as e:
        print(f"开仓失败: {str(e)}")
 
async def close_position(args, exchange):
    try:
        position_side = 'LONG' if position['side'] == 'buy' else 'SHORT'
        order = exchange.create_order( 
            symbol=args.symbol, 
            type='market',
            side='sell' if position['side'] == 'buy' else 'buy',
            amount=position['quantity'],
            params={'positionSide': position_side}
        )
        position.update({'opened':  False, 'entry_price': None})
        print("平仓成功！")
        
    except ccxt.BaseError as e:
        print(f"平仓失败: {str(e)}")
 
def parse_args():
    parser = argparse.ArgumentParser(description='币安永续合约监控交易工具')
    parser.add_argument('--symbol',  required=True, help='合约币对 如 BTC/USDT')
    parser.add_argument('--threshold',  type=Decimal, default=3,
                       help='涨跌幅阈值（百分比）')
    parser.add_argument('--stop-loss',  type=Decimal, default=3,
                       help='固定止损百分比')
    parser.add_argument('--trailing-stop',  type=Decimal, default=2,
                       help='回撤止损百分比')
    parser.add_argument('--quantity',  type=Decimal, required=True,
                       help='交易数量')
    return parser.parse_args() 
 
if __name__ == "__main__":
    args = parse_args()
    
    # 初始化交易所 
    exchange = ccxt.binance({ 
        'apiKey': input('请输入API Key: '),
        'secret': input('请输入Secret Key: '),
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True 
        }
    })
    
    # 加载市场数据 
    exchange.load_markets() 
    
    # 启动监控 
    asyncio.get_event_loop().run_until_complete( 
        monitor_price(args, exchange)
    )