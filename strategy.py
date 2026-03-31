"""
Торговые модули стратегии:
  - London Breakout (LB)
  - Overlap Momentum (OM)

Работает как с бэктест-данными, так и с live-данными.
"""

import pandas as pd

from config import (
    LONDON_BREAKOUT_START,
    LONDON_BREAKOUT_END,
    OVERLAP_START,
    OVERLAP_END,
    LB_SL_EXTRA_PIPS,
    LB_TP_MULTIPLIER,
    LB_MAX_HOLD_HOURS,
    OM_SL_PIPS,
    OM_TP_PIPS,
    OM_BODY_RATIO,
    OM_VOLUME_RATIO,
    OM_MAX_HOLD_HOURS,
    OM_BODY_LOOKBACK,
    OM_VOLUME_LOOKBACK,
    RSI_OVERLAP_MIN,
    RSI_OVERLAP_MAX,
    PIP_SIZE,
)


def check_london_breakout(candle: pd.Series, asian: dict,
                           data: pd.DataFrame, idx: int) -> dict | None:
    """
    Проверяет сигнал London Breakout на данной свече.
    Возвращает dict с параметрами сделки или None.
    """
    hour = candle["hour"]
    if hour < LONDON_BREAKOUT_START or hour > LONDON_BREAKOUT_END:
        return None

    close = candle["close"]
    asian_high = asian["asian_high"]
    asian_low = asian["asian_low"]
    range_pips = asian["range_pips"]
    ema = candle["ema21"]

    # Направление пробоя
    direction = None
    if close > asian_high:
        direction = "BUY"
    elif close < asian_low:
        direction = "SELL"
    else:
        return None

    # Фильтр: свеча направленная
    if direction == "BUY" and not candle["is_bullish"]:
        return None
    if direction == "SELL" and candle["is_bullish"]:
        return None

    # Фильтр: EMA(21)
    if direction == "BUY" and close <= ema:
        return None
    if direction == "SELL" and close >= ema:
        return None

    # SL и TP
    range_price = range_pips * PIP_SIZE
    sl_distance = range_price + LB_SL_EXTRA_PIPS * PIP_SIZE
    tp_distance = range_price * LB_TP_MULTIPLIER

    if direction == "BUY":
        sl = close - sl_distance
        tp = close + tp_distance
    else:
        sl = close + sl_distance
        tp = close - tp_distance

    sl_pips = round(sl_distance / PIP_SIZE, 1)
    tp_pips = round(tp_distance / PIP_SIZE, 1)

    return {
        "module": "LB",
        "direction": direction,
        "entry_price": close,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "max_hold_hours": LB_MAX_HOLD_HOURS,
        "entry_time": candle["datetime"],
        "entry_idx": idx,
        "asian_range_pips": range_pips,
    }


def check_overlap_momentum(candle: pd.Series,
                            data: pd.DataFrame, idx: int) -> dict | None:
    """
    Проверяет сигнал Overlap Momentum на данной свече.
    Возвращает dict с параметрами сделки или None.
    """
    hour = candle["hour"]
    if hour < OVERLAP_START or hour > OVERLAP_END:
        return None

    if idx < max(OM_BODY_LOOKBACK, OM_VOLUME_LOOKBACK):
        return None

    close = candle["close"]
    body = candle["body"]

    # Крупная свеча
    prev_bodies = data.iloc[idx - OM_BODY_LOOKBACK:idx]["body"]
    avg_body = prev_bodies.mean()
    if avg_body == 0 or body < avg_body * OM_BODY_RATIO:
        return None

    # Повышенный объём
    prev_volumes = data.iloc[idx - OM_VOLUME_LOOKBACK:idx]["volume"]
    avg_volume = prev_volumes.mean()
    if avg_volume == 0 or candle["volume"] < avg_volume * OM_VOLUME_RATIO:
        return None

    # RSI
    rsi = candle["rsi"]
    if pd.isna(rsi) or rsi < RSI_OVERLAP_MIN or rsi > RSI_OVERLAP_MAX:
        return None

    direction = "BUY" if candle["is_bullish"] else "SELL"

    sl_distance = OM_SL_PIPS * PIP_SIZE
    tp_distance = OM_TP_PIPS * PIP_SIZE

    if direction == "BUY":
        sl = close - sl_distance
        tp = close + tp_distance
    else:
        sl = close + sl_distance
        tp = close - tp_distance

    return {
        "module": "OM",
        "direction": direction,
        "entry_price": close,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "sl_pips": float(OM_SL_PIPS),
        "tp_pips": float(OM_TP_PIPS),
        "max_hold_hours": OM_MAX_HOLD_HOURS,
        "entry_time": candle["datetime"],
        "entry_idx": idx,
    }
