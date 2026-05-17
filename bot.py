import asyncio
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from aiohttp import web

from config import BOT_TOKEN, DOWNLOAD_FOLDER, PORT, MAX_TELEGRAM_FILE_MB


# Проверяем, что токен реально указан.
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Добавь токен бота в Environment Variables на Render.")

# Создаём папку для временных файлов.
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)

# Создаём бота и диспетчер aiogram.
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def health_check(request: web.Request) -> web.Response:
    """
    Простой HTTP-ответ для Render.
    Нужен, чтобы облако видело, что приложение работает.
    """
    return web.Response(text="Bot is running")


async def start_web_server() -> None:
    """
    Запускает маленький веб-сервер для Render.
    Сам Telegram-бот работает через polling отдельно.
    """
    app = web.Application()
    app.router.add_get("/", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()


async def run_blocking(func, *args):
    """
    Запускает тяжёлую синхронную функцию в отдельном потоке.
    Так бот не зависает во время yt-dlp или ffmpeg.
    """
    return await asyncio.to_thread(func, *args)


def safe_filename(name: str) -> str:
    """
    Очищает название файла от запрещённых символов.
    Это нужно, чтобы файл нормально сохранялся в Linux/Windows.
    """
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "audio"


def download_audio_from_url_sync(url: str, work_dir: Path) -> Path:
    """
    Скачивает аудио из ссылки через yt-dlp.
    Возвращает путь к готовому mp3-файлу.
    """
    output_template = str(work_dir / "%(title).120s.%(ext)s")

    # Настройки yt-dlp: берём лучший звук и сразу конвертируем в mp3.
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    # Скачиваем и конвертируем аудио.
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = safe_filename(info.get("title") or "audio")

    # Ищем готовый mp3-файл в рабочей папке.
    mp3_files = list(work_dir.glob("*.mp3"))
    if not mp3_files:
        raise FileNotFoundError("Не удалось создать mp3-файл.")

    # Переименовываем файл по названию видео.
    final_audio = work_dir / f"{title}.mp3"
    mp3_files[0].rename(final_audio)
    return final_audio


def extract_audio_from_video_sync(video_path: Path) -> Path:
    """
    Отделяет аудио дорожку от Telegram-видео через ffmpeg.
    Возвращает путь к mp3-файлу.
    """
    audio_path = video_path.with_suffix(".mp3")

    # Команда ffmpeg для извлечения аудио.
    command = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        "-y",
        str(audio_path),
    ]

    # Запускаем ffmpeg и проверяем ошибки.
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg не смог извлечь аудио из видео.")

    return audio_path


def cleanup_folder(folder: Path) -> None:
    """
    Удаляет временную папку после обработки.
    """
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """
    Обрабатывает команду /start.
    """
    await message.answer(
        "Привет. Отправь мне ссылку на видео или само видео.\n"
        "Я отделю аудио дорожку и пришлю mp3."
    )


@dp.message(F.text)
async def link_handler(message: Message) -> None:
    """
    Обрабатывает текстовые сообщения со ссылками.
    """
    url = message.text.strip()

    # Простая проверка, что пользователь прислал ссылку.
    if not url.startswith(("http://", "https://")):
        await message.answer("Пришли ссылку на видео или загрузи видео файлом.")
        return

    work_dir = Path(DOWNLOAD_FOLDER) / str(uuid.uuid4())
    work_dir.mkdir(parents=True, exist_ok=True)

    status = await message.answer("Скачиваю и извлекаю аудио...")

    try:
        # Скачиваем аудио через yt-dlp в отдельном потоке.
        audio_path = await run_blocking(download_audio_from_url_sync, url, work_dir)

        # Отправляем mp3 пользователю.
        await message.answer_audio(audio=FSInputFile(audio_path), title=audio_path.stem)
        await status.delete()

    except Exception as error:
        await message.answer(f"Ошибка обработки ссылки:\n{error}")

    finally:
        # Чистим временные файлы.
        cleanup_folder(work_dir)


@dp.message(F.video | F.document)
async def video_file_handler(message: Message) -> None:
    """
    Обрабатывает видео, отправленное в Telegram.
    Поддерживает обычное видео и видео как документ.
    """
    tg_file = message.video or message.document

    # Проверяем размер файла, чтобы бот не пытался обработать слишком тяжёлое видео.
    file_size_mb = tg_file.file_size / 1024 / 1024 if tg_file.file_size else 0
    if file_size_mb > MAX_TELEGRAM_FILE_MB:
        await message.answer(f"Файл слишком большой. Максимум: {MAX_TELEGRAM_FILE_MB} МБ.")
        return

    work_dir = Path(DOWNLOAD_FOLDER) / str(uuid.uuid4())
    work_dir.mkdir(parents=True, exist_ok=True)

    # Берём имя файла или создаём стандартное.
    original_name = getattr(tg_file, "file_name", None) or "telegram_video.mp4"
    safe_name = safe_filename(original_name)
    video_path = work_dir / safe_name

    status = await message.answer("Скачиваю видео из Telegram...")

    try:
        # Скачиваем файл из Telegram на сервер.
        file_info = await bot.get_file(tg_file.file_id)
        await bot.download_file(file_info.file_path, destination=video_path)

        await status.edit_text("Извлекаю аудио...")

        # Извлекаем аудио через ffmpeg.
        audio_path = await run_blocking(extract_audio_from_video_sync, video_path)

        # Отправляем mp3 пользователю.
        await message.answer_audio(audio=FSInputFile(audio_path), title=audio_path.stem)
        await status.delete()

    except Exception as error:
        await message.answer(f"Ошибка обработки видео:\n{error}")

    finally:
        # Чистим временные файлы.
        cleanup_folder(work_dir)


async def main() -> None:
    """
    Главная функция запуска приложения.
    Запускает веб-сервер Render и Telegram-бота.
    """
    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
