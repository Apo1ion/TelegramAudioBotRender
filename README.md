# TelegramAudioBotRender
Telegram-бот для извлечения аудио из видео. Бот принимает ссылки на видео с YouTube, VK, Rutube и других сайтов, а также видеофайлы напрямую из Telegram, после чего скачивает видео, отделяет аудиодорожку и отправляет пользователю готовый MP3-файл с оригинальным названием видео.

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
Бот поднят через Render: https://dashboard.render.com/login
