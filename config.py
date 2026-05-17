import os

# Токен бота берется из переменных окружения Render
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Папка для временных файлов
DOWNLOAD_FOLDER = "downloads"

# Максимальный размер файла для отправки в Telegram, в мегабайтах
MAX_FILE_SIZE_MB = 45
