import ccxt
import argparse
from config import load_config
def ContractTrade(exchange_name, api_key, api_secret, symbol, order_type, price, amount):
    pass

# 逐仓合约交易
# param symbol；开多/开空；倍率；仓位（0-1）;止盈价；止损价
def BinanceContractTrade(ex: ccxt.Exchange, symbol: str, side, leverage, amount: float, stopProfitPrice: float = None, stopLossPrice: float = None):
    ex.set_margin_mode('ISOLATED', symbol, params={'leverage': leverage})

    # 如果有止盈止损价，则设置止盈止损
    params = {}
    if stopProfitPrice is not None:
        params['takeProfitPrice'] = stopProfitPrice
    if stopLossPrice is not None:
        params['stopLossPrice'] = stopLossPrice
    

    order = ex.create_order(symbol, 'market', side, amount, None, params)

    print(order)


if __name__ == '__main__':
    config = load_config('config.yaml')

    my_config = config['exchanges']['binance']

    ex = ccxt.binance({
        'apiKey': my_config['api_key'],
        'secret': my_config['api_secret'],
    })

    ex.load_markets()
    
    BinanceContractTrade(ex, "BTC/USDT:USDT", "buy", )

