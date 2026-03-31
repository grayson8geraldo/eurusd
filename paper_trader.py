"""
Paper Trading движок.
Виртуальный баланс, открытие/закрытие сделок, журнал.
Состояние сохраняется в JSON между перезапусками бота.
"""

import json
import os
import csv
from datetime import datetime, timezone

from config import (
    INITIAL_BALANCE,
    LOT_TIERS,
    PIP_SIZE,
    PIP_VALUE_PER_LOT,
    STATE_FILE,
    JOURNAL_FILE,
    EVENING_CLOSE_HOUR,
)


class OpenTrade:
    """Активная (открытая) сделка."""

    def __init__(self, module: str, direction: str, entry_price: float,
                 sl: float, tp: float, sl_pips: float, tp_pips: float,
                 lot: float, entry_time: str, max_hold_hours: int,
                 asian_range_pips: float = 0):
        self.module = module
        self.direction = direction
        self.entry_price = entry_price
        self.sl = sl
        self.tp = tp
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.lot = lot
        self.entry_time = entry_time
        self.max_hold_hours = max_hold_hours
        self.asian_range_pips = asian_range_pips

    def check_price(self, current_price: float, high: float, low: float,
                    current_time: datetime) -> dict | None:
        """
        Проверяет, нужно ли закрыть сделку.
        Возвращает dict результата или None если сделка жива.
        """
        entry_dt = datetime.fromisoformat(self.entry_time)
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        hours_held = (current_time - entry_dt).total_seconds() / 3600

        if self.direction == "BUY":
            # SL
            if low <= self.sl:
                return self._close_result(self.sl, current_time, "SL")
            # TP
            if high >= self.tp:
                return self._close_result(self.tp, current_time, "TP")
        else:
            if high >= self.sl:
                return self._close_result(self.sl, current_time, "SL")
            if low <= self.tp:
                return self._close_result(self.tp, current_time, "TP")

        # Таймаут
        if hours_held >= self.max_hold_hours:
            return self._close_result(current_price, current_time, "TIMEOUT")

        # Конец дня 20:00 UTC
        if current_time.hour >= EVENING_CLOSE_HOUR:
            return self._close_result(current_price, current_time, "EOD")

        return None

    def _close_result(self, exit_price: float, exit_time: datetime, reason: str) -> dict:
        if self.direction == "BUY":
            pnl_pips = round((exit_price - self.entry_price) / PIP_SIZE, 1)
        else:
            pnl_pips = round((self.entry_price - exit_price) / PIP_SIZE, 1)

        pnl_usd = round(pnl_pips * self.lot * PIP_VALUE_PER_LOT, 2)

        return {
            "module": self.module,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "exit_price": round(exit_price, 5),
            "exit_time": exit_time.isoformat(),
            "exit_reason": reason,
            "sl": self.sl,
            "tp": self.tp,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "lot": self.lot,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
        }

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp": self.tp,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "lot": self.lot,
            "entry_time": self.entry_time,
            "max_hold_hours": self.max_hold_hours,
            "asian_range_pips": self.asian_range_pips,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OpenTrade":
        return cls(**d)


class PaperTrader:
    """Менеджер виртуального портфеля."""

    def __init__(self):
        self.balance = INITIAL_BALANCE
        self.open_trade: OpenTrade | None = None
        self.daily_lb_done = False
        self.daily_om_done = False
        self.daily_lb_stopped = False
        self.daily_om_stopped = False
        self.current_date = ""
        self.total_trades = 0
        self.total_pnl = 0.0

        self._load_state()

    def _load_state(self):
        """Загружает состояние из файла."""
        if not os.path.exists(STATE_FILE):
            self._save_state()
            return

        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)

            self.balance = state.get("balance", INITIAL_BALANCE)
            self.current_date = state.get("current_date", "")
            self.daily_lb_done = state.get("daily_lb_done", False)
            self.daily_om_done = state.get("daily_om_done", False)
            self.daily_lb_stopped = state.get("daily_lb_stopped", False)
            self.daily_om_stopped = state.get("daily_om_stopped", False)
            self.total_trades = state.get("total_trades", 0)
            self.total_pnl = state.get("total_pnl", 0.0)

            trade_data = state.get("open_trade")
            if trade_data:
                self.open_trade = OpenTrade.from_dict(trade_data)

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠ Ошибка чтения состояния: {e}, начинаю с нуля")
            self._save_state()

    def _save_state(self):
        """Сохраняет состояние в файл."""
        state = {
            "balance": self.balance,
            "current_date": self.current_date,
            "daily_lb_done": self.daily_lb_done,
            "daily_om_done": self.daily_om_done,
            "daily_lb_stopped": self.daily_lb_stopped,
            "daily_om_stopped": self.daily_om_stopped,
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "open_trade": self.open_trade.to_dict() if self.open_trade else None,
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def reset_daily(self, today: str):
        """Сбрасывает дневные счётчики если наступил новый день."""
        if self.current_date != today:
            self.current_date = today
            self.daily_lb_done = False
            self.daily_om_done = False
            self.daily_lb_stopped = False
            self.daily_om_stopped = False
            self._save_state()

    def get_lot(self) -> float:
        """Возвращает текущий лот по балансу."""
        for low, high, lot in LOT_TIERS:
            if low <= self.balance < high:
                return lot
        return LOT_TIERS[-1][2]

    def can_trade_lb(self) -> bool:
        return (not self.daily_lb_done
                and not self.daily_lb_stopped
                and self.open_trade is None
                and self.balance >= LOT_TIERS[0][0])

    def can_trade_om(self) -> bool:
        return (not self.daily_om_done
                and not self.daily_om_stopped
                and self.open_trade is None
                and self.balance >= LOT_TIERS[0][0])

    def open_position(self, signal: dict):
        """Открывает виртуальную позицию."""
        lot = self.get_lot()
        self.open_trade = OpenTrade(
            module=signal["module"],
            direction=signal["direction"],
            entry_price=signal["entry_price"],
            sl=signal["sl"],
            tp=signal["tp"],
            sl_pips=signal["sl_pips"],
            tp_pips=signal["tp_pips"],
            lot=lot,
            entry_time=signal["entry_time"].isoformat() if hasattr(signal["entry_time"], "isoformat") else str(signal["entry_time"]),
            max_hold_hours=signal["max_hold_hours"],
            asian_range_pips=signal.get("asian_range_pips", 0),
        )

        if signal["module"] == "LB":
            self.daily_lb_done = True
        else:
            self.daily_om_done = True

        self._save_state()

    def check_and_close(self, current_price: float, high: float, low: float,
                        current_time: datetime) -> dict | None:
        """Проверяет, нужно ли закрыть открытую сделку."""
        if self.open_trade is None:
            return None

        result = self.open_trade.check_price(current_price, high, low, current_time)
        if result is None:
            return None

        # Сделка закрыта
        self.balance += result["pnl_usd"]
        self.total_trades += 1
        self.total_pnl += result["pnl_usd"]

        if result["exit_reason"] == "SL":
            if result["module"] == "LB":
                self.daily_lb_stopped = True
            else:
                self.daily_om_stopped = True

        self.open_trade = None
        self._save_state()
        self._write_journal(result)

        return result

    def force_close(self, current_price: float) -> dict | None:
        """Принудительно закрывает позицию."""
        if self.open_trade is None:
            return None
        now = datetime.now(timezone.utc)
        result = self.open_trade._close_result(current_price, now, "MANUAL")
        self.balance += result["pnl_usd"]
        self.total_trades += 1
        self.total_pnl += result["pnl_usd"]
        self.open_trade = None
        self._save_state()
        self._write_journal(result)
        return result

    def _write_journal(self, trade: dict):
        """Записывает сделку в CSV-журнал."""
        file_exists = os.path.exists(JOURNAL_FILE)
        fieldnames = [
            "module", "direction", "entry_time", "entry_price",
            "sl", "tp", "sl_pips", "tp_pips", "lot",
            "exit_time", "exit_price", "exit_reason",
            "pnl_pips", "pnl_usd",
        ]
        with open(JOURNAL_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({k: trade.get(k, "") for k in fieldnames})

    def status_str(self) -> str:
        """Возвращает строку со статусом портфеля."""
        lines = [
            f"  Баланс: ${self.balance:.2f}",
            f"  Лот: {self.get_lot()}",
            f"  Всего сделок: {self.total_trades}",
            f"  Общий P&L: ${self.total_pnl:+.2f}",
        ]
        if self.open_trade:
            t = self.open_trade
            lines.append(f"  Открытая позиция: {t.module} {t.direction} @ {t.entry_price:.5f}"
                         f"  SL={t.sl:.5f}  TP={t.tp:.5f}  lot={t.lot}")
        else:
            lines.append("  Открытых позиций: нет")
        return "\n".join(lines)
