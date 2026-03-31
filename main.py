#!/usr/bin/env python3
"""
EUR/USD H1 Trading Bot — Бэктест.

Стратегия:
  1. London Breakout (08:00-11:00 UTC) — пробой Asian Range
  2. Overlap Momentum (13:00-15:00 UTC) — импульс на перекрытии сессий

Использование:
  python main.py                    # бэктест с отчётом
  python main.py --journal trades.csv  # сохранить журнал сделок в CSV
  python main.py --equity equity.csv   # сохранить equity curve в CSV
"""

import argparse
import os
import sys

from backtester import run_backtest, print_report


def main():
    parser = argparse.ArgumentParser(description="EUR/USD H1 Trading Bot Backtest")
    parser.add_argument("--data-dir", default=".", help="Директория с CSV-файлами (по умолчанию: текущая)")
    parser.add_argument("--journal", default=None, help="Сохранить журнал сделок в CSV-файл")
    parser.add_argument("--equity", default=None, help="Сохранить equity curve в CSV-файл")
    args = parser.parse_args()

    import pandas as pd

    trades, equity_df = run_backtest(args.data_dir)

    print_report(trades, equity_df)

    if args.journal and trades:
        df = pd.DataFrame(trades)
        df.to_csv(args.journal, index=False)
        print(f"\nЖурнал сделок сохранён: {args.journal}")

    if args.equity and not equity_df.empty:
        equity_df.to_csv(args.equity, index=False)
        print(f"Equity curve сохранена: {args.equity}")

    # Вывод последних 10 сделок
    if trades:
        print("\n" + "-" * 70)
        print("  ПОСЛЕДНИЕ 10 СДЕЛОК")
        print("-" * 70)
        for t in trades[-10:]:
            print(f"  {t['entry_time']}  {t['module']:2s}  {t['direction']:4s}  "
                  f"@ {t['entry_price']:.5f}  →  {t['exit_price']:.5f}  "
                  f"{t['exit_reason']:7s}  {t['pnl_pips']:+6.1f} пипс  "
                  f"${t['pnl_usd']:+7.2f}  lot={t['lot']}")


if __name__ == "__main__":
    main()
