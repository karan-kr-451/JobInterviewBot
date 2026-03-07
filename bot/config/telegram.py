"""
config.telegram - Telegram notification configuration.
"""

import os

# =============================================================================
# TELEGRAM
# =============================================================================

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN",  "7726524846:AAGMbkVvHrZROVTHX4giEYVZv_z2EGQX0Dw")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID",    "1571206699")
TELEGRAM_QUEUE_SIZE = 64

TELEGRAM_SEND_TIMEOUT  = 3
TELEGRAM_POLL_TIMEOUT  = 30
