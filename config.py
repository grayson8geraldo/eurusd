"""
Конфигурация live-бота EUR/USD H1.
Все параметры стратегии собраны в одном месте.
"""

# === API ===
# Получите бесплатный ключ на https://twelvedata.com/register
# Затем вставьте сюда или передайте через переменную окружения TWELVEDATA_API_KEY
TWELVEDATA_API_KEY = ""  # <-- Вставьте свой ключ сюда

SYMBOL = "EUR/USD"

# === Временные окна (UTC часы) ===
ASIAN_SESSION_START = 0        # 00:00 UTC
ASIAN_SESSION_END = 7          # 07:00 UTC

LONDON_BREAKOUT_START = 8      # 08:00 UTC
LONDON_BREAKOUT_END = 11       # 11:00 UTC

OVERLAP_START = 13             # 13:00 UTC
OVERLAP_END = 15               # 15:00 UTC

EVENING_CLOSE_HOUR = 20        # 20:00 UTC — закрываем всё

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
LB_SL_EXTRA_PIPS = 10
LB_TP_MULTIPLIER = 0.6
LB_MAX_HOLD_HOURS = 6

# === Overlap Momentum параметры ===
OM_SL_PIPS = 10
OM_TP_PIPS = 15
OM_BODY_RATIO = 1.2
OM_VOLUME_RATIO = 1.5
OM_MAX_HOLD_HOURS = 8
OM_BODY_LOOKBACK = 5
OM_VOLUME_LOOKBACK = 20

# === Риск-менеджмент ===
MAX_TRADES_PER_DAY = 2
FRIDAY_CLOSE_HOUR = 15

# === Лот-сайзинг по балансу ===
LOT_TIERS = [
    (200, 400, 0.05),
    (400, 800, 0.10),
    (800, 1500, 0.20),
    (1500, float('inf'), 0.30),
]

INITIAL_BALANCE = 200.0

# === Стоимость пипса ===
PIP_VALUE_PER_LOT = 10.0       # $10 за пипс при 1.0 лоте EUR/USD
PIP_SIZE = 0.0001              # 1 пипс = 0.0001

# === Файлы состояния ===
STATE_FILE = "bot_state.json"
JOURNAL_FILE = "trade_journal.csv"

# === Интервал проверки (секунды) ===
CHECK_INTERVAL_SECONDS = 30
