# 50QQ 期权套利工具

用于监控 ETF 期权套利机会，并记录到期结算结果。主程序包含盘后策略账本，支持四种策略模式；期权合约乘数按每张 10,000 份计算。

## 运行

安装 Python 依赖后，在项目目录运行：

```powershell
python -m pip install -r requirements.txt
python option_arbitrage_scanner.py
```

Windows 下也可以运行 `run_windows.bat`。

## 结算费用

盘后策略账本的“费用配置”可调整现货佣金率、期权买入开仓费、主动行权费和被动行权费。默认值如下：

| 费用 | 默认值 |
| --- | ---: |
| 现货佣金率 | 0.000100 |
| 买入开仓费 | 1.70 元/张 |
| 主动行权费 | 0.70 元/张 |
| 被动行权费 | 0.10 元/张 |

模式 1、4 按主动行权费计算；模式 2、3 按被动行权费计算。对应行权费按期权张数计入结算利润和公式。模式 2、3 不计买入开仓费及主动行权费。

## 打包

在 Windows 上运行 `build_windows_exe.bat`，生成的主程序位于 `dist/50qqScanner/50qqScanner.exe`。打包脚本会保留已有的 `strategy_ledger.json`。
