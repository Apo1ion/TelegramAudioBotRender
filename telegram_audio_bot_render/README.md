# Telegram Audio Bot

Бот принимает ссылку на видео или само видео и отправляет mp3-аудио дорожку.

## Что внутри

- Python
- aiogram 3.x
- yt-dlp
- ffmpeg
- Docker
- подготовка под Render

## Переменная окружения

На Render нужно добавить:

BOT_TOKEN=твой_токен_бота

## Локальный запуск

```bash
pip install -r requirements.txt
python bot.py
```

Для локального запуска нужен установленный ffmpeg.

## Запуск через Docker

```bash
docker build -t telegram-audio-bot .
docker run -e BOT_TOKEN=твой_токен_бота -p 10000:10000 telegram-audio-bot
```
