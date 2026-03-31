"""
Расчёт Asian Range для текущего дня.
Asian Session: 00:00 — 07:00 UTC.
"""

import pandas as pd
from datetime import date

from config import (
    ASIAN_SESSION_START,
    ASIAN_SESSION_END,
    ASIAN_RANGE_MIN_PIPS,
    ASIAN_RANGE_MAX_PIPS,
    PIP_SIZE,
)


def compute_asian_range_for_date(data: pd.DataFrame, target_date: date) -> dict | None:
    """
    Вычисляет Asian Range для конкретной даты.

    Возвращает dict или None если недостаточно данных.
    """
    asian_candles = data[
        (data["date"] == target_date) &
        (data["hour"] >= ASIAN_SESSION_START) &
        (data["hour"] < ASIAN_SESSION_END)
    ]

    if len(asian_candles) < 3:
        return None

    asian_high = asian_candles["high"].max()
    asian_low = asian_candles["low"].min()
    range_pips = round((asian_high - asian_low) / PIP_SIZE, 1)
    valid = ASIAN_RANGE_MIN_PIPS <= range_pips <= ASIAN_RANGE_MAX_PIPS

    return {
        "asian_high": asian_high,
        "asian_low": asian_low,
        "range_pips": range_pips,
        "valid": valid,
    }
