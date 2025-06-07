PerpetualContract.py

使用 argparse websockets ccxt写一个工具
能监控binance的价格，进行实时开单

参数有如下：

* 合约币对
* 上涨和下跌的幅度，默认值 3%
* 平仓条件： 默认在开仓价止损
* 回撤止损：
* 进入横盘后也需要平仓

主要逻辑为：合约条件市价单


基于上述要求写一个python工具，在一个python文件中写完整