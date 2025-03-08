import ccxt

def execute_arbitrage(symbol, a_exchange, b_exchange, amount, trade_fee_a, trade_fee_b, cross_chain_fee):
    """
    执行跨交易所套利操作，返回理论计算结果
    """
    # 加载市场信息并检查交易对是否存在
    a_exchange.load_markets()
    b_exchange.load_markets()
    
    if symbol not in a_exchange.markets:
        raise ValueError(f"交易对 {symbol} 在 {a_exchange.name} 不存在")
    if symbol not in b_exchange.markets:
        raise ValueError(f"交易对 {symbol} 在 {b_exchange.name} 不存在")
    
    # 获取市场精度
    market_a = a_exchange.market(symbol)
    market_b = b_exchange.market(symbol)
    
    # 获取订单簿数据
    a_orderbook = a_exchange.fetch_order_book(symbol)
    b_orderbook = b_exchange.fetch_order_book(symbol)
    
    a_ask = a_orderbook['asks'][0][0] if len(a_orderbook['asks']) > 0 else None
    b_bid = b_orderbook['bids'][0][0] if len(b_orderbook['bids']) > 0 else None
    
    if not a_ask or not b_bid:
        raise ValueError("无法获取有效价格")
    
    # 计算买入数量（考虑手续费）
    base_precision = market_a['precision']['base']
    getcontext().prec = 10  # 设置 Decimal 精度
    
    # 计算理论买入数量
    quote_amount = Decimal(str(amount))
    a_ask_dec = Decimal(str(a_ask))
    fee_multiplier_a = Decimal('1') - Decimal(str(trade_fee_a))
    
    base_bought = (quote_amount / a_ask_dec) * fee_multiplier_a
    base_after_transfer = base_bought - Decimal(str(cross_chain_fee))
    
    if base_after_transfer <= 0:
        raise ValueError("跨链后基础货币数量不足")
    
    # 计算卖出金额（考虑手续费）
    b_bid_dec = Decimal(str(b_bid))
    fee_multiplier_b = Decimal('1') - Decimal(str(trade_fee_b))
    quote_obtained = base_after_transfer * b_bid_dec * fee_multiplier_b
    
    profit = quote_obtained - quote_amount
    
    # 四舍五入到市场精度
    base_bought_rounded = round(base_bought, base_precision)
    quote_obtained_rounded = round(quote_obtained, market_b['precision']['quote'])
    profit_rounded = round(profit, market_b['precision']['quote'])
    
    return {
        'symbol': symbol,
        'buy_exchange': a_exchange.name,
        'sell_exchange': b_exchange.name,
        'buy_price': float(a_ask),
        'sell_price': float(b_bid),
        'base_bought': float(base_bought_rounded),
        'quote_obtained': float(quote_obtained_rounded),
        'profit': float(profit_rounded),
        'fees': {
            'trade_fee_a': trade_fee_a,
            'trade_fee_b': trade_fee_b,
            'cross_chain_fee': cross_chain_fee
        }
    }