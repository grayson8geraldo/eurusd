"""
Расчёт Asian Range для каждого торгового дня.
Asian Session: 00:00 — 07:00 UTC (свечи с hour 0..6, т.к. свеча 06:00 закрывается в 07:00).
"""

import pandas as pd

from config import (
    ASIAN_SESSION_START,
    ASIAN_SESSION_END,
    ASIAN_RANGE_MIN_PIPS,
    ASIAN_RANGE_MAX_PIPS,
    PIP_SIZE,
)


def compute_asian_ranges(data: pd.DataFrame) -> dict:
    """
    Для каждой даты вычисляет Asian Range.

    Возвращает dict: date -> {
        'asian_high': float,
        'asian_low': float,
        'range_pips': float,
        'valid': bool  (True если range в 15-60 пипсов)
    }
    """
    asian_candles = data[
        (data["hour"] >= ASIAN_SESSION_START) & (data["hour"] < ASIAN_SESSION_END)
    ]

    result = {}
    for date, group in asian_candles.groupby("date"):
        if len(group) < 3:
            continue

        asian_high = group["high"].max()
        asian_low = group["low"].min()
        range_pips = round((asian_high - asian_low) / PIP_SIZE, 1)
        valid = ASIAN_RANGE_MIN_PIPS <= range_pips <= ASIAN_RANGE_MAX_PIPS

        result[date] = {
            "asian_high": asian_high,
            "asian_low": asian_low,
            "range_pips": range_pips,
            "valid": valid,
        }

    return result
