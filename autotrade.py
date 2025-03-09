import argparse
import yaml
import ccxt
import time

def execute_arbitrage(symbol: str, a_exchange: ccxt.Exchange, b_exchange: ccxt.Exchange, base_amount: float, quote_amount: float = None):
    """执行跨交易所市价单套利交易。amount：为买入数量币的数量，不是USDT数量"""
    try:
        # 强制使用市价单交易， 市价单比限价单手续费要多。这里可以进行调参优化 限价单优惠买卖加低的手续费可能利润更高。可以自行调参测试

        # Fix bitget api 需要传createMarketBuyOrderRequiresPrice，否则是限价单
        buy_amount = base_amount
        a_params = {}
        if a_exchange.id == 'bitget':
            a_params={'createMarketBuyOrderRequiresPrice': False}
            buy_amount = quote_amount
        b_params = {}
        if b_exchange.id == 'bitget':
            b_params={'createMarketBuyOrderRequiresPrice': False}

        if quote_amount == None:
            quote_amount = base_amount

        buy_order = a_exchange.create_market_buy_order(symbol, buy_amount, a_params)
        sell_order = b_exchange.create_market_sell_order(symbol, base_amount, b_params)

        print("交易开始...")
        while True:
            buy_order = a_exchange.fetch_order(buy_order['id'], symbol)
            sell_order = b_exchange.fetch_order(sell_order['id'], symbol)

            if buy_order['status'] == 'closed' and sell_order['status'] == 'closed':
                break
            time.sleep(1)

            # 打印交易的进度
            print(f"交易进度: 买入 {buy_order['status']}，卖出 {sell_order['status']}")

        # 免手续费fee情况的处理
        buy_fee = 0.0
        if buy_order['fee'] is not None:
            buy_fee = float(buy_order['fee']['cost'])
        elif buy_order['fees']:
            buy_fee = sum(fee['cost'] for fee in buy_order['fees'])

        sell_fee = 0.0
        if sell_order['fee'] is not None:
            sell_fee = float(sell_order['fee']['cost'])
        elif sell_order['fees']:
            sell_fee = sum(fee['cost'] for fee in sell_order['fees'])


        buy_price = buy_order['average'] * buy_order['amount'] + buy_fee
        sell_price = sell_order['average']
        
        # 计算利润 从 buy_order 和 sell_order
        profit = buy_price * buy_order['amount'] + buy_fee - (sell_price * sell_order['amount'] - sell_fee)

        return {
            'buy_price': buy_price,
            'sell_price': sell_price,
            'final_quote': actual_sell_income,
            'profit': profit,
            'profitable': profit > 0,
            'buy_fee': buy_fee,
            'sell_fee': sell_fee,
            'coin': float(buy_order['amount']) - float(sell_order['amount']),
        }
    except ccxt.InsufficientFunds as e:
        raise ValueError(f"资金不足: {str(e)}")
    except ccxt.NetworkError as e:
        raise ValueError(f"网络错误: {str(e)}")
    except ccxt.ExchangeError as e:
        raise ValueError(f"交易所错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"交易执行失败: {str(e)}")

def load_exchange(config, exchange_name):
    """从配置加载交易所实例"""
    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange_params = {
            'apiKey': config['exchanges'][exchange_name]['api_key'],
            'secret': config['exchanges'][exchange_name]['api_secret'],
            'enableRateLimit': True
        }
        
        if 'password' in config['exchanges'][exchange_name]:
            exchange_params['password'] = config['exchanges'][exchange_name]['password']
        
        return exchange_class(exchange_params)
    except (KeyError, AttributeError) as e:
        raise ValueError(f"交易所配置错误: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='跨交易所市价套利工具')
    parser.add_argument('--symbol', required=True, help='交易对，例如 BTC/USDT')
    parser.add_argument('--buy', required=True, dest='buy_exchange', help='买入交易所名称')
    parser.add_argument('--sell', required=True, dest='sell_exchange', help='卖出交易所名称')
    parser.add_argument('--amount', type=float, required=True, help='投入金额（基础货币）不是计价货币BTC/USDT，BTC是基础货币，USDT是计价货币')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    args = parser.parse_args()

    # 初始化部分
    try:
        with open(args.config) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"错误：配置文件 {args.config} 未找到")
        return

    try:
        buy_ex = load_exchange(config, args.buy_exchange)
        sell_ex = load_exchange(config, args.sell_exchange)
    except ValueError as e:
        print(e)
        return

    # 执行套利交易的代码部分
    try:
        result = execute_arbitrage(
            symbol=args.symbol,
            a_exchange=buy_ex,
            b_exchange=sell_ex,
            amount=args.amount,
        )
    except Exception as e:
        print(f"执行错误: {str(e)}")
        return

    # 格式化输出
    print(f"\n套利交易结果 ({args.symbol})")
    print("="*40)
    print(f"[买入] {args.buy_exchange.ljust(10)} 均价: {result['buy_price']:.8f}")
    print(f"[卖出] {args.sell_exchange.ljust(10)} 均价: {result['sell_price']:.8f}")
    print("-"*40)
    print(f"实际买入数量: {result['base_acquired']:.8f}")
    print(f"最终获得金额: {result['final_quote']:.2f}")
    print(f"投入金额: {args.amount:.2f}")
    print("="*40)
    status = "成功盈利" if result['profitable'] else "亏损"
    print(f"实际利润: {result['profit']:.2f} ({status})")

if __name__ == '__main__':
    main()