#!/usr/bin/env python3
"""
EUR/USD H1 Live Trading Bot (Paper Trading).

Работает в реальном времени на живых данных с виртуальным балансом $200.
Стратегия: London Breakout + Overlap Momentum.

Запуск:
    python bot.py              — запуск бота
    python bot.py --status     — показать текущий статус
    python bot.py --reset      — сбросить баланс на $200
    python bot.py --journal    — показать журнал сделок
"""

import argparse
import time
import signal as signal_module
import sys
import os
from datetime import datetime, timezone, date

from config import (
    CHECK_INTERVAL_SECONDS,
    ASIAN_RANGE_MIN_PIPS,
    ASIAN_RANGE_MAX_PIPS,
    INITIAL_BALANCE,
    STATE_FILE,
    JOURNAL_FILE,
    EVENING_CLOSE_HOUR,
)
from live_data import fetch_h1_candles, get_current_price
from asian_range import compute_asian_range_for_date
from strategy import check_london_breakout, check_overlap_momentum
from news_filter import should_skip_trading
from paper_trader import PaperTrader


# Глобальный флаг для graceful shutdown
running = True


def signal_handler(sig, frame):
    global running
    print("\n\n  Останавливаю бота...")
    running = False


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          EUR/USD H1 LIVE TRADING BOT (Paper)                ║
║          London Breakout + Overlap Momentum                 ║
╚══════════════════════════════════════════════════════════════╝
""")


def show_status(trader: PaperTrader):
    """Показывает текущий статус портфеля."""
    print("\n📊 СТАТУС ПОРТФЕЛЯ")
    print("─" * 50)
    print(trader.status_str())
    print("─" * 50)


def show_journal():
    """Показывает журнал сделок."""
    if not os.path.exists(JOURNAL_FILE):
        print("Журнал пуст — сделок ещё не было.")
        return

    import pandas as pd
    df = pd.read_csv(JOURNAL_FILE)
    if df.empty:
        print("Журнал пуст.")
        return

    print(f"\n📋 ЖУРНАЛ СДЕЛОК ({len(df)} записей)")
    print("─" * 90)
    print(f"{'Время входа':>20s}  {'Мод':>3s}  {'Напр':>4s}  {'Вход':>9s}  "
          f"{'Выход':>9s}  {'Причина':>7s}  {'Пипсы':>7s}  {'P&L':>8s}")
    print("─" * 90)

    for _, row in df.iterrows():
        entry_t = str(row['entry_time'])[:19]
        print(f"  {entry_t:>19s}  {row['module']:>3s}  {row['direction']:>4s}  "
              f"{row['entry_price']:>9.5f}  {row['exit_price']:>9.5f}  "
              f"{row['exit_reason']:>7s}  {row['pnl_pips']:>+7.1f}  "
              f"${row['pnl_usd']:>+7.2f}")

    print("─" * 90)
    print(f"  Итого: {df['pnl_pips'].sum():+.1f} пипсов  |  ${df['pnl_usd'].sum():+.2f}")
    print(f"  Win Rate: {len(df[df['pnl_pips'] > 0]) / len(df) * 100:.1f}%")


def reset_bot():
    """Сброс бота к начальному состоянию."""
    for f in [STATE_FILE, JOURNAL_FILE]:
        if os.path.exists(f):
            os.remove(f)
    print(f"Бот сброшен. Баланс: ${INITIAL_BALANCE:.2f}")


def run_bot():
    """Основной цикл бота."""
    global running

    signal_module.signal(signal_module.SIGINT, signal_handler)
    signal_module.signal(signal_module.SIGTERM, signal_handler)

    print_banner()

    trader = PaperTrader()
    show_status(trader)

    last_processed_hour = None
    data = None
    last_data_fetch = None
    last_price_check = None

    print("\n  Бот запущен. Ctrl+C для остановки.\n")

    while running:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()
            today_str = today.isoformat()
            current_hour = now.hour

            # Сброс дневных счётчиков
            trader.reset_daily(today_str)

            # Обновляем данные каждые 10 минут или при первом запуске
            if data is None or last_data_fetch is None or \
               (now - last_data_fetch).total_seconds() > 600:
                try:
                    print(f"  [{now.strftime('%H:%M:%S')} UTC] Загрузка данных...")
                    data = fetch_h1_candles(days_back=30)
                    last_data_fetch = now
                    print(f"  Загружено {len(data)} свечей. "
                          f"Последняя: {data['datetime'].iloc[-1]}")
                except Exception as e:
                    print(f"  ❌ Ошибка загрузки данных: {e}")
                    time.sleep(120)
                    continue

            # === Проверяем открытую позицию каждые 2 минуты ===
            if trader.open_trade is not None:
                should_check_price = (
                    last_price_check is None or
                    (now - last_price_check).total_seconds() > 120
                )
                if should_check_price:
                    try:
                        price = get_current_price()
                        last_price_check = now
                        if price > 0:
                            result = trader.check_and_close(
                                current_price=price,
                                high=price,
                                low=price,
                                current_time=now,
                            )
                            if result:
                                _print_trade_closed(result, trader)
                    except Exception as e:
                        print(f"  ⚠ Ошибка проверки позиции: {e}")

            # === Проверяем сигналы только на закрытии новой H1 свечи ===
            # Обрабатываем свечу один раз — в первые 5 минут после закрытия
            candle_just_closed = (now.minute < 5 and current_hour != last_processed_hour)

            if not candle_just_closed:
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            last_processed_hour = current_hour
            print(f"\n  ⏰ [{now.strftime('%Y-%m-%d %H:%M')} UTC] Анализ свечи H1...")

            # Проверка новостей
            skip, reason = should_skip_trading()
            if skip:
                print(f"  ⛔ Пропускаем: {reason}")
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            # Получаем последнюю завершённую свечу
            completed = data[data["hour"] < current_hour]
            if completed.empty:
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            last_candle = data.iloc[-1]
            last_idx = len(data) - 1

            # Показываем свечу
            direction_emoji = "🟢" if last_candle["is_bullish"] else "🔴"
            print(f"  {direction_emoji} O={last_candle['open']:.5f} "
                  f"H={last_candle['high']:.5f} "
                  f"L={last_candle['low']:.5f} "
                  f"C={last_candle['close']:.5f} "
                  f"V={last_candle['volume']:.0f}")
            print(f"  EMA21={last_candle['ema21']:.5f}  "
                  f"RSI={last_candle['rsi']:.1f}")

            # Asian Range
            asian = compute_asian_range_for_date(data, today)
            if asian:
                valid_str = "✅" if asian["valid"] else "❌"
                print(f"  Asian Range: {asian['range_pips']:.1f} пипсов "
                      f"(H={asian['asian_high']:.5f} L={asian['asian_low']:.5f}) {valid_str}")

            # === МОДУЛЬ 1: London Breakout ===
            if trader.can_trade_lb() and asian and asian["valid"]:
                signal = check_london_breakout(last_candle, asian, data, last_idx)
                if signal:
                    _open_trade(trader, signal)

            # === МОДУЛЬ 2: Overlap Momentum ===
            if trader.can_trade_om():
                signal = check_overlap_momentum(last_candle, data, last_idx)
                if signal:
                    _open_trade(trader, signal)

            # Статус
            if current_hour in (8, 12, 16, 20):
                show_status(trader)

            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            time.sleep(60)

    # Завершение
    print("\n" + "=" * 50)
    print("  Бот остановлен.")
    show_status(trader)
    if trader.open_trade:
        print("  ⚠ Есть открытая позиция! Она сохранена и будет")
        print("    проверена при следующем запуске.")
    print("=" * 50)


def _open_trade(trader: PaperTrader, signal: dict):
    """Открывает сделку и выводит информацию."""
    trader.open_position(signal)
    t = trader.open_trade
    print(f"\n  {'='*50}")
    print(f"  🔔 ОТКРЫТА СДЕЛКА: {t.module} {t.direction}")
    print(f"  Вход: {t.entry_price:.5f}  |  Лот: {t.lot}")
    print(f"  SL: {t.sl:.5f} ({t.sl_pips:.1f} пипсов)")
    print(f"  TP: {t.tp:.5f} ({t.tp_pips:.1f} пипсов)")
    print(f"  Макс. удержание: {t.max_hold_hours} часов")
    print(f"  {'='*50}\n")


def _print_trade_closed(result: dict, trader: PaperTrader):
    """Выводит информацию о закрытой сделке."""
    emoji = "✅" if result["pnl_pips"] > 0 else "❌"
    print(f"\n  {'='*50}")
    print(f"  {emoji} ЗАКРЫТА СДЕЛКА: {result['module']} {result['direction']}")
    print(f"  Вход: {result['entry_price']:.5f} → Выход: {result['exit_price']:.5f}")
    print(f"  Причина: {result['exit_reason']}")
    print(f"  Результат: {result['pnl_pips']:+.1f} пипсов  |  ${result['pnl_usd']:+.2f}")
    print(f"  Баланс: ${trader.balance:.2f}")
    print(f"  {'='*50}\n")


def main():
    parser = argparse.ArgumentParser(
        description="EUR/USD H1 Live Trading Bot (Paper Trading)"
    )
    parser.add_argument("--status", action="store_true",
                        help="Показать текущий статус портфеля")
    parser.add_argument("--journal", action="store_true",
                        help="Показать журнал сделок")
    parser.add_argument("--reset", action="store_true",
                        help="Сбросить бота (баланс $200)")
    args = parser.parse_args()

    if args.reset:
        reset_bot()
        return

    if args.journal:
        show_journal()
        return

    if args.status:
        trader = PaperTrader()
        show_status(trader)
        return

    run_bot()


if __name__ == "__main__":
    main()
