"""
Конфигурация торгового бота EUR/USD H1.
Все параметры стратегии собраны в одном месте.
"""

# === Временные окна (UTC часы) ===
ASIAN_SESSION_START = 0   # 00:00 UTC
ASIAN_SESSION_END = 7     # 07:00 UTC (последняя свеча азиатской сессии)

LONDON_BREAKOUT_START = 8   # 08:00 UTC
LONDON_BREAKOUT_END = 11    # 11:00 UTC (проверяем свечи закрывающиеся в 09-12)

OVERLAP_START = 13  # 13:00 UTC
OVERLAP_END = 15    # 15:00 UTC (проверяем свечи закрывающиеся в 14-16)

EVENING_CLOSE_HOUR = 20  # 20:00 UTC — закрываем всё

# === Asian Range ===
ASIAN_RANGE_MIN_PIPS = 15
ASIAN_RANGE_MAX_PIPS = 60

# === EMA ===
EMA_PERIOD = 21

# === RSI ===
RSI_PERIOD = 14
RSI_OVERLAP_MIN = 35
RSI_OVERLAP_MAX = 70

# === London Breakout параметры ===
LB_SL_EXTRA_PIPS = 10          # Ширина Asian Range + 10 пипсов
LB_TP_MULTIPLIER = 0.6         # TP = Asian Range × 0.6
LB_MAX_HOLD_HOURS = 6          # Закрыть через 6 часов

# === Overlap Momentum параметры ===
OM_SL_PIPS = 10                # Фиксированный SL = 10 пипсов
OM_TP_PIPS = 15                # Фиксированный TP = 15 пипсов
OM_BODY_RATIO = 1.2            # Тело свечи в 1.2+ раз больше средних
OM_VOLUME_RATIO = 1.5          # Объём в 1.5+ раз больше среднего
OM_MAX_HOLD_HOURS = 8          # Закрыть через 8 часов
OM_BODY_LOOKBACK = 5           # Кол-во свечей для сравнения тела
OM_VOLUME_LOOKBACK = 20        # Кол-во свечей для сравнения объёма

# === Риск-менеджмент ===
MAX_TRADES_PER_DAY = 2         # Максимум 2 сделки (1 LB + 1 OM)
FRIDAY_CLOSE_HOUR = 15         # В пятницу не открывать после 15:00 UTC

# === Лот-сайзинг по балансу ===
LOT_TIERS = [
    (200, 400, 0.05),
    (400, 800, 0.10),
    (800, 1500, 0.20),
    (1500, float('inf'), 0.30),
]

INITIAL_BALANCE = 200.0        # Стартовый баланс

# === Стоимость пипса ===
PIP_VALUE_PER_LOT = 10.0       # $10 за пипс при 1.0 лоте EUR/USD
PIP_SIZE = 0.0001              # 1 пипс = 0.0001 для EUR/USD

# === Новостные дни (для бэктеста — список дат в формате 'YYYY-MM-DD') ===
# В реальной торговле нужно подключать экономический календарь.
# Здесь можно вручную добавить даты NFP, ECB, Fed, CPI.
NEWS_DATES = set()
