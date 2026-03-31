"""
Бэктестер стратегии EUR/USD H1.
Проходит по данным свеча за свечой, эмулируя реальную торговлю.
"""

import pandas as pd
import numpy as np
from datetime import timedelta

from config import (
    FRIDAY_CLOSE_HOUR,
    EVENING_CLOSE_HOUR,
    MAX_TRADES_PER_DAY,
    LOT_TIERS,
    INITIAL_BALANCE,
    PIP_VALUE_PER_LOT,
    PIP_SIZE,
    NEWS_DATES,
)
from data_loader import load_all_data
from asian_range import compute_asian_ranges
from strategy import check_london_breakout, check_overlap_momentum


class Trade:
    """Представляет одну сделку."""

    def __init__(self, signal: dict, lot: float, entry_candle_idx: int):
        self.module = signal["module"]
        self.direction = signal["direction"]
        self.entry_price = signal["entry_price"]
        self.sl = signal["sl"]
        self.tp = signal["tp"]
        self.sl_pips = signal["sl_pips"]
        self.tp_pips = signal["tp_pips"]
        self.lot = lot
        self.entry_time = signal["entry_time"]
        self.entry_idx = entry_candle_idx
        self.max_hold_hours = signal["max_hold_hours"]

        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None  # 'TP', 'SL', 'TIMEOUT', 'EOD'
        self.pnl_pips = 0.0
        self.pnl_usd = 0.0

    def check_candle(self, candle: pd.Series, idx: int) -> bool:
        """
        Проверяет, закрывается ли сделка на данной свече.
        Возвращает True если сделка закрыта.
        """
        high = candle["high"]
        low = candle["low"]
        close = candle["close"]
        candle_time = candle["datetime"]

        hours_held = (candle_time - self.entry_time).total_seconds() / 3600

        if self.direction == "BUY":
            # Проверяем SL (цена могла упасть до SL внутри свечи)
            if low <= self.sl:
                self._close(self.sl, candle_time, "SL")
                return True
            # Проверяем TP
            if high >= self.tp:
                self._close(self.tp, candle_time, "TP")
                return True
        else:  # SELL
            # Проверяем SL
            if high >= self.sl:
                self._close(self.sl, candle_time, "SL")
                return True
            # Проверяем TP
            if low <= self.tp:
                self._close(self.tp, candle_time, "TP")
                return True

        # Таймаут по часам
        if hours_held >= self.max_hold_hours:
            self._close(close, candle_time, "TIMEOUT")
            return True

        # Закрытие в 20:00 UTC (конец дня)
        if candle["hour"] >= EVENING_CLOSE_HOUR:
            self._close(close, candle_time, "EOD")
            return True

        return False

    def _close(self, exit_price: float, exit_time, reason: str):
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason

        if self.direction == "BUY":
            self.pnl_pips = round((exit_price - self.entry_price) / PIP_SIZE, 1)
        else:
            self.pnl_pips = round((self.entry_price - exit_price) / PIP_SIZE, 1)

        self.pnl_usd = round(self.pnl_pips * self.lot * PIP_VALUE_PER_LOT, 2)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "direction": self.direction,
            "entry_time": self.entry_time,
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp": self.tp,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "lot": self.lot,
            "exit_time": self.exit_time,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "pnl_pips": self.pnl_pips,
            "pnl_usd": self.pnl_usd,
        }


def get_lot_size(balance: float) -> float:
    """Определяет лот по текущему балансу."""
    for low, high, lot in LOT_TIERS:
        if low <= balance < high:
            return lot
    return LOT_TIERS[-1][2]


def run_backtest(data_dir: str = ".") -> tuple[list[dict], pd.DataFrame]:
    """
    Запускает бэктест по всем данным.

    Возвращает:
        - список сделок (list of dict)
        - DataFrame с equity curve
    """
    print("Загрузка данных...")
    data = load_all_data(data_dir)
    print(f"  Загружено {len(data)} свечей H1")
    print(f"  Период: {data['datetime'].iloc[0]} — {data['datetime'].iloc[-1]}")

    print("Расчёт Asian Ranges...")
    asian_ranges = compute_asian_ranges(data)
    print(f"  Вычислено {len(asian_ranges)} дней")
    valid_days = sum(1 for v in asian_ranges.values() if v["valid"])
    print(f"  Дней с валидным Asian Range (15-60 пипсов): {valid_days}")

    balance = INITIAL_BALANCE
    trades: list[Trade] = []
    open_trades: list[Trade] = []
    equity_curve = []

    # Счётчики по дням
    daily_lb_done = {}  # date -> bool
    daily_om_done = {}  # date -> bool
    daily_lb_stopped = {}  # date -> bool (стоп сработал — модуль закрыт на день)
    daily_om_stopped = {}  # date -> bool

    print("Запуск бэктеста...")

    for idx in range(len(data)):
        candle = data.iloc[idx]
        date = candle["date"]
        hour = candle["hour"]
        weekday = candle["weekday"]

        # Проверяем открытые сделки
        still_open = []
        for trade in open_trades:
            closed = trade.check_candle(candle, idx)
            if closed:
                balance += trade.pnl_usd
                trades.append(trade)
                # Если стоп сработал — модуль закрыт на день
                if trade.exit_reason == "SL":
                    if trade.module == "LB":
                        daily_lb_stopped[date] = True
                    else:
                        daily_om_stopped[date] = True
            else:
                still_open.append(trade)
        open_trades = still_open

        # Запись equity
        unrealized = 0.0
        for t in open_trades:
            if t.direction == "BUY":
                unrealized += (candle["close"] - t.entry_price) / PIP_SIZE * t.lot * PIP_VALUE_PER_LOT
            else:
                unrealized += (t.entry_price - candle["close"]) / PIP_SIZE * t.lot * PIP_VALUE_PER_LOT
        equity_curve.append({
            "datetime": candle["datetime"],
            "balance": balance,
            "equity": balance + unrealized,
        })

        # === Фильтры: не открывать новые сделки ===

        # Новостные дни
        date_str = str(date)
        if date_str in NEWS_DATES:
            continue

        # Пятница после 15:00
        if weekday == 4 and hour >= FRIDAY_CLOSE_HOUR:
            continue

        # Баланс слишком мал
        if balance < LOT_TIERS[0][0]:
            continue

        # Asian Range для сегодня
        asian = asian_ranges.get(date)
        if asian is None:
            continue

        lot = get_lot_size(balance)

        # === МОДУЛЬ 1: London Breakout ===
        if (asian["valid"]
                and not daily_lb_done.get(date, False)
                and not daily_lb_stopped.get(date, False)
                and not open_trades):  # не открываем если уже есть позиция

            signal = check_london_breakout(candle, asian, data, idx)
            if signal:
                trade = Trade(signal, lot, idx)
                open_trades.append(trade)
                daily_lb_done[date] = True

        # === МОДУЛЬ 2: Overlap Momentum ===
        # OM работает даже если Asian Range невалиден (пропускаем только LB)
        if (not daily_om_done.get(date, False)
                and not daily_om_stopped.get(date, False)
                and not open_trades):  # не открываем если уже есть позиция

            signal = check_overlap_momentum(candle, data, idx)
            if signal:
                trade = Trade(signal, lot, idx)
                open_trades.append(trade)
                daily_om_done[date] = True

    # Закрываем оставшиеся сделки по последней цене
    if open_trades:
        last_candle = data.iloc[-1]
        for trade in open_trades:
            trade._close(last_candle["close"], last_candle["datetime"], "END")
            balance += trade.pnl_usd
            trades.append(trade)

    trade_dicts = [t.to_dict() for t in trades]
    equity_df = pd.DataFrame(equity_curve)

    return trade_dicts, equity_df


def print_report(trades: list[dict], equity_df: pd.DataFrame):
    """Печатает подробный отчёт по бэктесту."""
    if not trades:
        print("\nНет сделок за период.")
        return

    df = pd.DataFrame(trades)

    total = len(df)
    wins = len(df[df["pnl_pips"] > 0])
    losses = len(df[df["pnl_pips"] < 0])
    breakeven = len(df[df["pnl_pips"] == 0])
    win_rate = wins / total * 100

    total_pips = df["pnl_pips"].sum()
    total_usd = df["pnl_usd"].sum()
    avg_win = df[df["pnl_pips"] > 0]["pnl_pips"].mean() if wins else 0
    avg_loss = df[df["pnl_pips"] < 0]["pnl_pips"].mean() if losses else 0

    final_balance = INITIAL_BALANCE + total_usd
    max_equity = equity_df["equity"].max()
    min_equity = equity_df["equity"].min()
    max_drawdown_pct = (1 - min_equity / max_equity) * 100 if max_equity > 0 else 0

    # Расчёт максимальной просадки от пика
    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max)
    max_drawdown_abs = drawdown.min()
    peak_at_max_dd = running_max[drawdown.idxmin()]
    max_dd_pct_from_peak = abs(max_drawdown_abs) / peak_at_max_dd * 100 if peak_at_max_dd > 0 else 0

    # По модулям
    lb = df[df["module"] == "LB"]
    om = df[df["module"] == "OM"]

    print("\n" + "=" * 70)
    print("           ОТЧЁТ ПО БЭКТЕСТУ EUR/USD H1")
    print("=" * 70)
    print(f"  Начальный баланс:      ${INITIAL_BALANCE:.2f}")
    print(f"  Конечный баланс:       ${final_balance:.2f}")
    print(f"  Прибыль/убыток:        ${total_usd:.2f} ({total_usd / INITIAL_BALANCE * 100:+.1f}%)")
    print(f"  Макс. просадка:        ${abs(max_drawdown_abs):.2f} ({max_dd_pct_from_peak:.1f}% от пика)")
    print()
    print(f"  Всего сделок:          {total}")
    print(f"  Прибыльных:            {wins} ({win_rate:.1f}%)")
    print(f"  Убыточных:             {losses}")
    print(f"  Безубыточных:          {breakeven}")
    print()
    print(f"  Всего пипсов:          {total_pips:+.1f}")
    print(f"  Средний выигрыш:       {avg_win:+.1f} пипсов")
    print(f"  Средний проигрыш:      {avg_loss:+.1f} пипсов")
    if avg_loss != 0:
        print(f"  Profit Factor:         {abs(df[df['pnl_pips'] > 0]['pnl_usd'].sum() / df[df['pnl_pips'] < 0]['pnl_usd'].sum()):.2f}")

    print()
    print("-" * 70)
    print("  МОДУЛЬ: London Breakout (LB)")
    print("-" * 70)
    if len(lb):
        lb_wins = len(lb[lb["pnl_pips"] > 0])
        print(f"  Сделок:    {len(lb)}")
        print(f"  Win Rate:  {lb_wins / len(lb) * 100:.1f}%")
        print(f"  Пипсов:    {lb['pnl_pips'].sum():+.1f}")
        print(f"  P&L:       ${lb['pnl_usd'].sum():+.2f}")
        print(f"  Выходы:    TP={len(lb[lb['exit_reason'] == 'TP'])}, "
              f"SL={len(lb[lb['exit_reason'] == 'SL'])}, "
              f"TIMEOUT={len(lb[lb['exit_reason'] == 'TIMEOUT'])}, "
              f"EOD={len(lb[lb['exit_reason'] == 'EOD'])}")
    else:
        print("  Нет сделок")

    print()
    print("-" * 70)
    print("  МОДУЛЬ: Overlap Momentum (OM)")
    print("-" * 70)
    if len(om):
        om_wins = len(om[om["pnl_pips"] > 0])
        print(f"  Сделок:    {len(om)}")
        print(f"  Win Rate:  {om_wins / len(om) * 100:.1f}%")
        print(f"  Пипсов:    {om['pnl_pips'].sum():+.1f}")
        print(f"  P&L:       ${om['pnl_usd'].sum():+.2f}")
        print(f"  Выходы:    TP={len(om[om['exit_reason'] == 'TP'])}, "
              f"SL={len(om[om['exit_reason'] == 'SL'])}, "
              f"TIMEOUT={len(om[om['exit_reason'] == 'TIMEOUT'])}, "
              f"EOD={len(om[om['exit_reason'] == 'EOD'])}")
    else:
        print("  Нет сделок")

    print()
    print("-" * 70)
    print("  РАСПРЕДЕЛЕНИЕ ПО ПРИЧИНАМ ЗАКРЫТИЯ")
    print("-" * 70)
    for reason in ["TP", "SL", "TIMEOUT", "EOD", "END"]:
        subset = df[df["exit_reason"] == reason]
        if len(subset):
            print(f"  {reason:10s}  {len(subset):4d} сделок  |  {subset['pnl_pips'].sum():+8.1f} пипсов  |  ${subset['pnl_usd'].sum():+8.2f}")

    print()
    print("-" * 70)
    print("  ПОМЕСЯЧНАЯ СТАТИСТИКА")
    print("-" * 70)
    df["month"] = pd.to_datetime(df["entry_time"]).dt.to_period("M")
    monthly = df.groupby("month").agg(
        trades=("pnl_pips", "count"),
        pips=("pnl_pips", "sum"),
        usd=("pnl_usd", "sum"),
    )
    for period, row in monthly.iterrows():
        wr = len(df[(df["month"] == period) & (df["pnl_pips"] > 0)]) / row["trades"] * 100
        print(f"  {str(period):10s}  {int(row['trades']):3d} сделок  |  {row['pips']:+7.1f} пипсов  |  ${row['usd']:+8.2f}  |  WR: {wr:.0f}%")

    print("=" * 70)
