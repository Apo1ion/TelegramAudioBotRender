import os

# Токен Telegram-бота берём из переменной окружения Render.
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Папка для временных видео и аудио файлов.
DOWNLOAD_FOLDER = "downloads"

# Порт нужен Render, чтобы сервис считался запущенным.
PORT = int(os.getenv("PORT", "10000"))

# Максимальный размер Telegram-файла в мегабайтах.
MAX_TELEGRAM_FILE_MB = 50
