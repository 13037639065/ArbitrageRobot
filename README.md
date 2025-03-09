# 自动套利机器人

## 简介

本项目是一个自动套利机器人，基于Python语言开发，使用的是Python的ccxt,websocket,requests库，完成跨交易所套利
推荐使用conda避免环境问题
推荐 Python 3.12.9

## 功能

- 自动获取交易所的行情数据
- 计算套利机会
- 自动下单

## 使用方法

1. 安装Python环境
2. 安装cctx库
3. 修改配置文件config.json，配置交易所的API密钥和API密钥密码
4. 运行main.py文件



## 注意事项

- 本项目仅供学习和研究使用，不保证套利成功率
- 使用本项目进行套利交易，请自行承担风险

## 联系方式

- 邮箱：code-dream@qq.com

## 使用命令

### 安装环境

``` shell
conda create -n freqtrade python=3.12.9
conda activate freqtrade
pip3 install ccxt requests pyyaml websockets
```

### 工具使用

``` shell
# 默认是模拟交易
python3 main.py --symbol TRUMP/USDT --exchanges binance bitget --threshold 0.3

# 实盘交易需要注意交易所的一些限制，程序出错崩溃应该立刻停止止损。真实交易存在滑点
python3 main.py --symbol TRUMP/USDT --exchanges binance bitget --threshold 0.3 --real-trade
```

## TODO

验证能跑通的交易所有

- [ √ ] binance
- [ √ ] bitget
- [ √ ] okx
- [ ] htx
