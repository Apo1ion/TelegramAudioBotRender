import asyncio
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

from config import BOT_TOKEN, DOWNLOAD_FOLDER, MAX_FILE_SIZE_MB


# Проверяем, что токен добавлен в переменные окружения
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Добавь его в Environment Variables на Render.")

# Создаем папку для временных загрузок
Path(DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# Создаем объект Telegram-бота
bot = Bot(token=BOT_TOKEN)

# Создаем диспетчер aiogram
dp = Dispatcher()


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """
    Отправляет стартовое сообщение пользователю.
    """

    await message.answer(
        "Отправь ссылку на видео или само видео.\n"
        "Я отделю аудио и пришлю MP3."
    )


def clean_filename(name: str) -> str:
    """
    Очищает название файла от запрещенных символов.
    """

    # Удаляем символы, которые могут ломать путь к файлу
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)

    # Ограничиваем длину имени файла
    return cleaned.strip()[:120] or "audio"


def get_file_size_mb(path: str) -> float:
    """
    Возвращает размер файла в мегабайтах.
    """

    return os.path.getsize(path) / 1024 / 1024


def make_job_folder() -> str:
    """
    Создает отдельную временную папку для одной задачи.
    """

    job_id = str(uuid.uuid4())
    job_folder = os.path.join(DOWNLOAD_FOLDER, job_id)
    os.makedirs(job_folder, exist_ok=True)
    return job_folder


async def run_blocking(func, *args):
    """
    Запускает тяжелую синхронную функцию в отдельном потоке.
    """

    return await asyncio.to_thread(func, *args)


def download_video_from_url_sync(url: str, job_folder: str) -> str:
    """
    Скачивает видео по ссылке через yt-dlp.
    Возвращает путь к скачанному файлу.
    """

    # Шаблон имени файла с названием видео
    output_template = os.path.join(job_folder, "%(title).120s.%(ext)s")

    # Основные настройки yt-dlp с мягким обходом блокировок YouTube
    ydl_opts = {
        "outtmpl": output_template,
        "format": "bv*+ba/best/bestvideo+bestaudio",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage"],
            }
        },
    }

    # Скачиваем видео
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    # Ищем реальный скачанный файл в папке задачи
    files = [
        os.path.join(job_folder, file)
        for file in os.listdir(job_folder)
        if not file.endswith((".part", ".ytdl"))
    ]

    # Если файлов нет, значит загрузка сорвалась
    if not files:
        raise RuntimeError("Видео не было скачано.")

    # Возвращаем самый крупный файл как основной видеофайл
    return max(files, key=os.path.getsize)


async def download_video_from_url(url: str, job_folder: str) -> str:
    """
    Асинхронная обертка для скачивания видео.
    """

    return await run_blocking(download_video_from_url_sync, url, job_folder)


async def extract_audio(video_path: str) -> str:
    """
    Извлекает аудио из видео через ffmpeg.
    """

    # Создаем путь для MP3 с тем же названием
    base_name = os.path.splitext(video_path)[0]
    audio_path = base_name + ".mp3"

    # Команда ffmpeg для извлечения аудио
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "44100",
        "-y",
        audio_path,
    ]

    # Запускаем ffmpeg без вывода лишних логов
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Ждем завершения ffmpeg
    await process.communicate()

    # Проверяем, что файл реально создан
    if not os.path.exists(audio_path):
        raise RuntimeError("Не получилось извлечь аудио.")

    return audio_path


async def send_audio_file(message: Message, audio_path: str) -> None:
    """
    Отправляет аудио пользователю с проверкой размера.
    """

    # Проверяем размер файла перед отправкой
    if get_file_size_mb(audio_path) > MAX_FILE_SIZE_MB:
        await message.answer(
            f"Аудио получилось больше {MAX_FILE_SIZE_MB} МБ. "
            "Telegram может не принять такой файл на бесплатном облаке."
        )
        return

    # Отправляем MP3 как аудио
    await message.answer_audio(audio=FSInputFile(audio_path))


def get_friendly_error(error: Exception) -> str:
    """
    Превращает техническую ошибку в понятный текст.
    """

    error_text = str(error)

    # Отдельно объясняем частую ошибку YouTube
    if "Sign in to confirm" in error_text or "not a bot" in error_text:
        return (
            "YouTube заблокировал скачивание с облачного сервера и требует подтверждение, "
            "что это не бот.\n\n"
            "Я уже использую усиленные настройки yt-dlp, но иногда этого недостаточно.\n"
            "Решение: использовать другой сайт, прислать видео файлом, добавить cookies YouTube "
            "или перенести бота на VPS/хостинг с другим IP."
        )

    # Общая ошибка для остальных случаев
    return f"Ошибка обработки:\n{error_text}"


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    """
    Обрабатывает текстовые сообщения и ищет в них ссылку.
    """

    # Достаем первую ссылку из сообщения
    match = URL_PATTERN.search(message.text or "")

    # Если ссылки нет, просим отправить ссылку или видео
    if not match:
        await message.answer("Отправь ссылку на видео или само видео.")
        return

    url = match.group(0)
    job_folder = make_job_folder()

    try:
        await message.answer("Скачиваю видео...")

        # Скачиваем видео по ссылке
        video_path = await download_video_from_url(url, job_folder)

        await message.answer("Извлекаю аудио...")

        # Извлекаем аудио из видео
        audio_path = await extract_audio(video_path)

        # Отправляем готовый MP3
        await send_audio_file(message, audio_path)

    except Exception as error:
        await message.answer(get_friendly_error(error))

    finally:
        # Удаляем временную папку задачи
        shutil.rmtree(job_folder, ignore_errors=True)


@dp.message(F.video)
async def video_handler(message: Message) -> None:
    """
    Обрабатывает видеофайлы, отправленные прямо в Telegram.
    """

    job_folder = make_job_folder()

    try:
        await message.answer("Скачиваю видео из Telegram...")

        # Получаем информацию о файле в Telegram
        telegram_file = await bot.get_file(message.video.file_id)

        # Берем оригинальное имя видео, если оно есть
        original_name = message.video.file_name or "telegram_video.mp4"
        safe_name = clean_filename(original_name)

        # Путь для сохранения видео
        video_path = os.path.join(job_folder, safe_name)

        # Скачиваем видео из Telegram
        await bot.download_file(telegram_file.file_path, video_path)

        await message.answer("Извлекаю аудио...")

        # Извлекаем аудио из видео
        audio_path = await extract_audio(video_path)

        # Отправляем готовый MP3
        await send_audio_file(message, audio_path)

    except Exception as error:
        await message.answer(get_friendly_error(error))

    finally:
        # Удаляем временную папку задачи
        shutil.rmtree(job_folder, ignore_errors=True)


@dp.message(F.document)
async def document_handler(message: Message) -> None:
    """
    Обрабатывает видео, отправленные как документ.
    """

    # Проверяем MIME-тип документа
    mime_type: Optional[str] = message.document.mime_type

    if not mime_type or not mime_type.startswith("video/"):
        await message.answer("Это не видеофайл. Отправь видео или ссылку.")
        return

    job_folder = make_job_folder()

    try:
        await message.answer("Скачиваю видеофайл...")

        # Получаем файл документа в Telegram
        telegram_file = await bot.get_file(message.document.file_id)

        # Берем имя документа
        original_name = message.document.file_name or "video.mp4"
        safe_name = clean_filename(original_name)

        # Путь для сохранения документа
        video_path = os.path.join(job_folder, safe_name)

        # Скачиваем документ
        await bot.download_file(telegram_file.file_path, video_path)

        await message.answer("Извлекаю аудио...")

        # Извлекаем аудио
        audio_path = await extract_audio(video_path)

        # Отправляем MP3
        await send_audio_file(message, audio_path)

    except Exception as error:
        await message.answer(get_friendly_error(error))

    finally:
        # Удаляем временную папку задачи
        shutil.rmtree(job_folder, ignore_errors=True)


async def main() -> None:
    """
    Запускает бота в режиме polling.
    """

    print("Бот запущен")

    # Удаляем старые webhook-настройки, чтобы polling работал стабильно
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем постоянный опрос Telegram
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
