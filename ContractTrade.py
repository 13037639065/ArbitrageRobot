import ccxt
import argparse
from config import load_config
def ContractTrade(exchange_name, api_key, api_secret, symbol, order_type, price, amount):
    pass

# 逐仓合约交易
# param symbol；开多/开空；倍率；仓位（0-1）;止盈价；止损价
def BinanceContractTrade(ex: ccxt.Exchange, symbol: str, order_type: str, price: float, amount: float, stopProfitPrice: float = None, stopLossPrice: float = None):
    print
    
    if order_type == 'limit':
        order = ex.create_order(symbol, order_type, 'buy', amount, price)
    elif order_type == 'market':
        order = ex.create_order(symbol, order_type, 'buy', amount)
    else:
        raise ValueError(f"Unsupported order type: {order_type}")

    # 设置止盈和止损
    if stopProfitPrice is not None:
        ex.create_order(symbol, 'limit', 'sell', amount, stopProfitPrice, {'stopPrice': stopProfitPrice})
    if stopLossPrice is not None:
        ex.create_order(symbol, 'stop_loss_limit', 'sell', amount, stopLossPrice, {'stopPrice': stopLossPrice})


if __name__ == '__main__':
    config = load_config('config.yaml')

    my_config = config['exchanges']['binance']

    ex = ccxt.binance({
        'apiKey': my_config['api_key'],
        'secret': my_config['api_secret'],
    })

    print(ex.load_markets())

    # ContractTrade(args.exchange, args.api_key, args.api_secret, args.symbol, args.order_type, args.price, args.amount)