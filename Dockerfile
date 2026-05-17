# Используем официальный Python-образ
FROM python:3.11-slim

# Устанавливаем ffmpeg и сертификаты для HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую папку приложения
WORKDIR /app

# Копируем файл зависимостей отдельно для кеширования установки
COPY requirements.txt .

# Обновляем pip и устанавливаем Python-зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Копируем остальные файлы проекта
COPY . .

# Запускаем Telegram-бота
CMD ["python", "bot.py"]
