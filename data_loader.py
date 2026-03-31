"""
Загрузка и подготовка данных EUR/USD H1 из CSV-файлов.
"""

import glob
import os

import pandas as pd

from indicators import calc_ema, calc_rsi
from config import EMA_PERIOD, RSI_PERIOD


def load_all_data(data_dir: str = ".") -> pd.DataFrame:
    """Загрузить все CSV-файлы EUR/USD H1 и объединить в один DataFrame."""
    pattern = os.path.join(data_dir, "EUR-USD_Hour_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        raise FileNotFoundError(f"Не найдены CSV-файлы по шаблону: {pattern}")

    frames = []
    for f in files:
        df = pd.read_csv(f)
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)

    # Парсинг даты
    data["datetime"] = pd.to_datetime(data["UTC"], format="%d.%m.%Y %H:%M:%S.%f UTC")
    data = data.sort_values("datetime").reset_index(drop=True)

    # Стандартизация колонок
    data = data.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # Добавляем вспомогательные колонки
    data["date"] = data["datetime"].dt.date
    data["hour"] = data["datetime"].dt.hour
    data["weekday"] = data["datetime"].dt.weekday  # 0=Mon, 4=Fri

    # Технические индикаторы
    data["ema21"] = calc_ema(data["close"], EMA_PERIOD)
    data["rsi"] = calc_rsi(data["close"], RSI_PERIOD)

    # Характеристики свечи
    data["body"] = abs(data["close"] - data["open"])
    data["is_bullish"] = data["close"] > data["open"]

    return data[["datetime", "date", "hour", "weekday",
                  "open", "high", "low", "close", "volume",
                  "ema21", "rsi", "body", "is_bullish"]].copy()
