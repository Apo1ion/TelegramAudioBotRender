# Берём официальный лёгкий образ Python.
FROM python:3.11-slim

# Устанавливаем ffmpeg для работы с аудио и видео.
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Создаём рабочую папку внутри контейнера.
WORKDIR /app

# Копируем список библиотек отдельно, чтобы Docker быстрее пересобирался.
COPY requirements.txt .

# Устанавливаем Python-библиотеки.
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер.
COPY . .

# Открываем порт, который Render передаст через переменную PORT.
EXPOSE 10000

# Запускаем бота.
CMD ["python", "bot.py"]
