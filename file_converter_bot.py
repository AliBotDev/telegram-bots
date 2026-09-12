import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

MAX_FILE_SIZE_MB = int(
    os.getenv("MAX_FILE_SIZE_MB", "20")
)

MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

RATE_LIMIT_REQUESTS = int(
    os.getenv("RATE_LIMIT_REQUESTS", "10")
)

RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
)

FILE_TTL_MINUTES = int(
    os.getenv("FILE_TTL_MINUTES", "1440")
)

STORAGE_DIR = Path(
    os.getenv("STORAGE_DIR", "./storage")
)

STORAGE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DB_PATH = Path("file_converter.db")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("file_converter_bot")


# ============================================================
# AIROGRAM
# ============================================================

dp = Dispatcher()


# ============================================================
# GLOBAL STATE
# ============================================================

job_queue: asyncio.Queue = asyncio.Queue()

queue_workers = []

shutdown_event = asyncio.Event()

rate_limits: dict[int, list[float]] = {}

user_last_upload: dict[int, str] = {}

job_locks: dict[str, asyncio.Lock] = {}


# ============================================================
# FILE TYPES
# ============================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
}

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".json",
    ".csv",
    *IMAGE_EXTENSIONS,
}


# ============================================================
# EXCEPTIONS
# ============================================================

class UserFileError(Exception):
    pass


class FileValidationError(UserFileError):
    pass


class ConversionError(UserFileError):
    pass


# ============================================================
# DATABASE
# ============================================================

def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database() -> None:
    with get_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                path TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                upload_id TEXT NOT NULL,
                conversion TEXT NOT NULL,
                status TEXT NOT NULL,
                output_path TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(upload_id)
                    REFERENCES uploads(id)
                    ON DELETE CASCADE
            )
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_uploads_created_at
            ON uploads(created_at)
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_jobs_created_at
            ON jobs(created_at)
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_jobs_status
            ON jobs(status)
            """
        )

        db.commit()

    logger.info("SQLite database initialized.")


# ============================================================
# HELPERS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


def sanitize_filename(filename: str) -> str:
    filename = Path(filename).name

    filename = re.sub(
        r"[^a-zA-Z0-9а-яА-ЯёЁ._-]+",
        "_",
        filename,
    )

    filename = filename.strip(" .")

    if not filename:
        filename = "file"

    return filename[:200]


def safe_unlink(
    path: Optional[str | Path],
) -> None:

    if not path:
        return

    try:
        file_path = Path(path)

        if (
            file_path.exists()
            and file_path.is_file()
        ):
            file_path.unlink()

    except Exception:

        logger.exception(
            "Failed to delete file: %s",
            path,
        )


def get_file_size(
    path: Path,
) -> int:

    try:
        return path.stat().st_size

    except FileNotFoundError:
        return 0


def ensure_file_size(
    path: Path,
) -> None:

    size = get_file_size(path)

    if size <= 0:

        raise FileValidationError(
            "Файл пустой."
        )

    if size > MAX_FILE_SIZE:

        raise FileValidationError(
            f"Файл превышает лимит "
            f"{MAX_FILE_SIZE_MB} MB."
        )


# ============================================================
# MIME DETECTION WITHOUT LIBMAGIC
# ============================================================

def detect_mime(
    path: Path,
) -> str:

    try:

        with path.open("rb") as file:

            header = file.read(64)

        # PDF
        if header.startswith(
            b"%PDF-"
        ):
            return "application/pdf"

        # JPEG
        if header.startswith(
            b"\xFF\xD8\xFF"
        ):
            return "image/jpeg"

        # PNG
        if header.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            return "image/png"

        # GIF
        if (
            header.startswith(b"GIF87a")
            or header.startswith(b"GIF89a")
        ):
            return "image/gif"

        # WEBP
        if (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        ):
            return "image/webp"

        # BMP
        if header.startswith(
            b"BM"
        ):
            return "image/bmp"

        # Text / JSON
        try:

            text = path.read_text(
                encoding="utf-8",
                errors="strict",
            )

            stripped = text.lstrip()

            if (
                stripped.startswith("{")
                or stripped.startswith("[")
            ):

                try:
                    json.loads(text)

                    return "application/json"

                except json.JSONDecodeError:
                    pass

            return "text/plain"

        except UnicodeDecodeError:

            return "application/octet-stream"

    except Exception as exc:

        raise FileValidationError(
            f"Не удалось определить тип файла: {exc}"
        ) from exc


# ============================================================
# CONTENT VALIDATION
# ============================================================

def validate_pdf(
    path: Path,
) -> None:

    try:

        reader = PdfReader(
            str(path)
        )

        if reader.is_encrypted:

            raise FileValidationError(
                "Зашифрованные PDF "
                "не поддерживаются."
            )

        _ = len(
            reader.pages
        )

    except FileValidationError:
        raise

    except Exception as exc:

        raise FileValidationError(
            "Файл имеет расширение PDF, "
            "но не является корректным PDF."
        ) from exc


def validate_image(
    path: Path,
) -> None:

    try:

        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            image.load()

    except Exception as exc:

        raise FileValidationError(
            "Файл не является корректным изображением."
        ) from exc


def validate_json(
    path: Path,
) -> None:

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            json.load(file)

    except UnicodeDecodeError as exc:

        raise FileValidationError(
            "JSON должен быть UTF-8."
        ) from exc

    except json.JSONDecodeError as exc:

        raise FileValidationError(
            f"Некорректный JSON: {exc}"
        ) from exc


def validate_csv(
    path: Path,
) -> None:

    try:

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.reader(file)

            try:

                next(reader)

            except StopIteration:

                raise FileValidationError(
                    "CSV-файл пустой."
                )

    except UnicodeDecodeError as exc:

        raise FileValidationError(
            "CSV должен быть UTF-8."
        ) from exc


def validate_text(
    path: Path,
) -> None:

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            file.read(
                1024 * 1024
            )

    except UnicodeDecodeError as exc:

        raise FileValidationError(
            "Текстовый файл должен быть UTF-8."
        ) from exc


def validate_mime(
    path: Path,
    extension: str,
) -> str:

    mime = detect_mime(path)

    if extension in {
        ".jpg",
        ".jpeg",
    }:

        if mime != "image/jpeg":

            raise FileValidationError(
                f"Ожидался JPEG, "
                f"но найден {mime}."
            )

    elif extension == ".png":

        if mime != "image/png":

            raise FileValidationError(
                f"Ожидался PNG, "
                f"но найден {mime}."
            )

    elif extension == ".webp":

        if mime != "image/webp":

            raise FileValidationError(
                f"Ожидался WebP, "
                f"но найден {mime}."
            )

    elif extension == ".gif":

        if mime != "image/gif":

            raise FileValidationError(
                f"Ожидался GIF, "
                f"но найден {mime}."
            )

    elif extension == ".bmp":

        if mime != "image/bmp":

            raise FileValidationError(
                f"Ожидался BMP, "
                f"но найден {mime}."
            )

    elif extension == ".pdf":

        if mime != "application/pdf":

            raise FileValidationError(
                f"Ожидался PDF, "
                f"но найден {mime}."
            )

    elif extension == ".json":

        if mime not in {
            "application/json",
            "text/plain",
        }:

            raise FileValidationError(
                f"Ожидался JSON, "
                f"но найден {mime}."
            )

    elif extension in {
        ".txt",
        ".md",
        ".csv",
    }:

        if mime not in {
            "text/plain",
            "application/octet-stream",
        }:

            raise FileValidationError(
                f"Ожидался текстовый файл, "
                f"но найден {mime}."
            )

    return mime


def validate_file_content(
    path: Path,
    extension: str,
) -> str:

    extension = extension.lower()

    if extension not in ALLOWED_EXTENSIONS:

        raise FileValidationError(
            "Данный формат не поддерживается."
        )

    ensure_file_size(path)

    mime = validate_mime(
        path,
        extension,
    )

    if extension == ".pdf":

        validate_pdf(path)

    elif extension in IMAGE_EXTENSIONS:

        validate_image(path)

    elif extension == ".json":

        validate_json(path)

    elif extension == ".csv":

        validate_csv(path)

    elif extension in {
        ".txt",
        ".md",
    }:

        validate_text(path)

    return mime


# ============================================================
# CONVERTERS
# ============================================================

def convert_pdf_to_txt(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        reader = PdfReader(
            str(input_path)
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as output:

            for number, page in enumerate(
                reader.pages,
                start=1,
            ):

                output.write(
                    f"===== PAGE {number} =====\n"
                )

                output.write(
                    page.extract_text() or ""
                )

                output.write(
                    "\n\n"
                )

    except Exception as exc:

        raise ConversionError(
            f"PDF → TXT: {exc}"
        ) from exc


def convert_image_to_jpg(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with Image.open(
            input_path
        ) as image:

            image = image.convert(
                "RGB"
            )

            image.save(
                output_path,
                "JPEG",
                quality=95,
            )

    except Exception as exc:

        raise ConversionError(
            f"Изображение → JPG: {exc}"
        ) from exc


def convert_image_to_webp(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with Image.open(
            input_path
        ) as image:

            image.save(
                output_path,
                "WEBP",
                quality=95,
            )

    except Exception as exc:

        raise ConversionError(
            f"Изображение → WebP: {exc}"
        ) from exc


def convert_json_format(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with input_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

            file.write(
                "\n"
            )

    except Exception as exc:

        raise ConversionError(
            f"JSON format: {exc}"
        ) from exc


def convert_json_minify(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with input_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

    except Exception as exc:

        raise ConversionError(
            f"JSON minify: {exc}"
        ) from exc


def convert_csv_to_json(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with input_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(
                file
            )

            rows = list(reader)

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                rows,
                file,
                indent=2,
                ensure_ascii=False,
            )

            file.write(
                "\n"
            )

    except Exception as exc:

        raise ConversionError(
            f"CSV → JSON: {exc}"
        ) from exc


def convert_to_zip(
    input_path: Path,
    output_path: Path,
) -> None:

    try:

        with zipfile.ZipFile(
            output_path,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as archive:

            archive.write(
                input_path,
                arcname=input_path.name,
            )

    except Exception as exc:

        raise ConversionError(
            f"ZIP: {exc}"
        ) from exc


CONVERSIONS = {
    "pdf_txt": {
        "title": "PDF → TXT",
        "extensions": {".pdf"},
        "suffix": ".txt",
        "function": convert_pdf_to_txt,
    },

    "image_jpg": {
        "title": "Изображение → JPG",
        "extensions": IMAGE_EXTENSIONS,
        "suffix": ".jpg",
        "function": convert_image_to_jpg,
    },

    "image_webp": {
        "title": "Изображение → WebP",
        "extensions": IMAGE_EXTENSIONS,
        "suffix": ".webp",
        "function": convert_image_to_webp,
    },

    "json_format": {
        "title": "JSON → красивый JSON",
        "extensions": {".json"},
        "suffix": ".formatted.json",
        "function": convert_json_format,
    },

    "json_minify": {
        "title": "JSON → Minified JSON",
        "extensions": {".json"},
        "suffix": ".min.json",
        "function": convert_json_minify,
    },

    "csv_json": {
        "title": "CSV → JSON",
        "extensions": {".csv"},
        "suffix": ".json",
        "function": convert_csv_to_json,
    },

    "zip": {
        "title": "Файл → ZIP",
        "extensions": ALLOWED_EXTENSIONS,
        "suffix": ".zip",
        "function": convert_to_zip,
    },
}


# ============================================================
# STORAGE
# ============================================================

def create_upload_path(
    user_id: int,
    filename: str,
) -> Path:

    safe_name = sanitize_filename(
        filename
    )

    user_directory = (
        STORAGE_DIR / str(user_id)
    )

    user_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return user_directory / (
        f"{uuid.uuid4()}_{safe_name}"
    )


def create_output_path(
    input_path: Path,
    job_id: str,
    conversion: str,
) -> Path:

    config = CONVERSIONS[
        conversion
    ]

    return input_path.parent / (
        f"{input_path.stem}_"
        f"{job_id[:8]}"
        f"{config['suffix']}"
    )


# ============================================================
# RATE LIMIT
# ============================================================

def check_rate_limit(
    user_id: int,
) -> bool:

    now = asyncio.get_running_loop().time()

    timestamps = rate_limits.get(
        user_id,
        [],
    )

    timestamps = [
        timestamp
        for timestamp in timestamps
        if now - timestamp
        < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(timestamps) >= RATE_LIMIT_REQUESTS:

        rate_limits[user_id] = timestamps

        return False

    timestamps.append(now)

    rate_limits[user_id] = timestamps

    return True


# ============================================================
# LOCK
# ============================================================

def get_job_lock(
    job_id: str,
) -> asyncio.Lock:

    lock = job_locks.get(
        job_id
    )

    if lock is None:

        lock = asyncio.Lock()

        job_locks[job_id] = lock

    return lock


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def save_upload(
    upload_id: str,
    user_id: int,
    filename: str,
    path: Path,
    extension: str,
    size: int,
) -> None:

    with get_db() as db:

        db.execute(
            """
            INSERT INTO uploads (
                id,
                user_id,
                original_filename,
                path,
                extension,
                size_bytes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                user_id,
                filename,
                str(path),
                extension,
                size,
                utc_iso(),
            ),
        )

        db.commit()


def get_upload(
    upload_id: str,
):

    with get_db() as db:

        return db.execute(
            """
            SELECT *
            FROM uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()


def save_job(
    job_id: str,
    user_id: int,
    upload_id: str,
    conversion: str,
) -> None:

    with get_db() as db:

        db.execute(
            """
            INSERT INTO jobs (
                id,
                user_id,
                upload_id,
                conversion,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                upload_id,
                conversion,
                "pending",
                utc_iso(),
            ),
        )

        db.commit()


def get_job(
    job_id: str,
):

    with get_db() as db:

        return db.execute(
            """
            SELECT
                j.*,
                u.original_filename,
                u.path AS input_path,
                u.extension,
                u.size_bytes
            FROM jobs j
            JOIN uploads u
                ON u.id = j.upload_id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()


def update_job_status(
    job_id: str,
    status: str,
    output_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:

    with get_db() as db:

        db.execute(
            """
            UPDATE jobs
            SET
                status = ?,
                output_path = COALESCE(
                    ?,
                    output_path
                ),
                error_message = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                output_path,
                error_message,
                (
                    utc_iso()
                    if status
                    in {
                        "completed",
                        "failed",
                    }
                    else None
                ),
                job_id,
            ),
        )

        db.commit()


# ============================================================
# QUEUE
# ============================================================

async def worker(
    worker_id: int,
):

    logger.info(
        "Queue worker %s started.",
        worker_id,
    )

    while not shutdown_event.is_set():

        try:

            job_id = await asyncio.wait_for(
                job_queue.get(),
                timeout=1,
            )

        except asyncio.TimeoutError:

            continue

        try:

            await process_job(
                job_id
            )

        except Exception:

            logger.exception(
                "Worker %s failed processing job %s",
                worker_id,
                job_id,
            )

        finally:

            job_queue.task_done()

    logger.info(
        "Queue worker %s stopped.",
        worker_id,
    )


# ============================================================
# PROCESS JOB
# ============================================================

async def process_job(
    job_id: str,
):

    lock = get_job_lock(
        job_id
    )

    # Local distributed-style protection
    # for the running process.
    async with lock:

        job = await asyncio.to_thread(
            get_job,
            job_id,
        )

        if not job:
            logger.warning(
                "Job %s not found.",
                job_id,
            )
            return

        if job["status"] == "completed":
            return

        input_path = Path(
            job["input_path"]
        )

        extension = (
            job["extension"]
            .lower()
        )

        conversion = (
            job["conversion"]
        )

        try:

            if not input_path.exists():

                raise UserFileError(
                    "Исходный файл не найден."
                )

            if conversion not in CONVERSIONS:

                raise UserFileError(
                    "Неизвестная конвертация."
                )

            config = CONVERSIONS[
                conversion
            ]

            if extension not in config[
                "extensions"
            ]:

                raise UserFileError(
                    "Эта конвертация "
                    "недоступна для файла."
                )

            # Re-check size and content.
            mime = await asyncio.to_thread(
                validate_file_content,
                input_path,
                extension,
            )

            logger.info(
                "Job %s validation passed. MIME=%s",
                job_id,
                mime,
            )

            output_path = (
                create_output_path(
                    input_path,
                    job_id,
                    conversion,
                )
            )

            safe_unlink(
                output_path
            )

            await asyncio.to_thread(
                update_job_status,
                job_id,
                "processing",
                str(output_path),
                None,
            )

            converter = config[
                "function"
            ]

            await asyncio.to_thread(
                converter,
                input_path,
                output_path,
            )

            ensure_file_size(
                output_path
            )

            await asyncio.to_thread(
                update_job_status,
                job_id,
                "completed",
                str(output_path),
                None,
            )

            logger.info(
                "Job %s completed.",
                job_id,
            )

        except UserFileError as exc:

            logger.warning(
                "Job %s failed: %s",
                job_id,
                exc,
            )

            await asyncio.to_thread(
                update_job_status,
                job_id,
                "failed",
                None,
                str(exc),
            )

        except Exception as exc:

            logger.exception(
                "Unexpected error in job %s",
                job_id,
            )

            await asyncio.to_thread(
                update_job_status,
                job_id,
                "failed",
                None,
                str(exc),
            )

        # Send result.
        updated_job = await asyncio.to_thread(
            get_job,
            job_id,
        )

        if not updated_job:
            return

        bot = current_bot

        if bot is None:
            return

        if updated_job["status"] == "completed":

            output_path = Path(
                updated_job["output_path"]
            )

            if output_path.exists():

                await bot.send_document(
                    chat_id=updated_job["user_id"],
                    document=FSInputFile(
                        output_path
                    ),
                    caption=(
                        "✅ Готово!\n\n"
                        f"📄 "
                        f"{updated_job['original_filename']}\n"
                        f"⚙️ "
                        f"{CONVERSIONS[conversion]['title']}"
                    ),
                )

        elif updated_job["status"] == "failed":

            await bot.send_message(
                updated_job["user_id"],
                (
                    "❌ Не удалось обработать файл.\n\n"
                    f"{updated_job['error_message']}"
                ),
            )


# ============================================================
# CLEANUP
# ============================================================

async def cleanup_old_files():

    while not shutdown_event.is_set():

        try:

            await asyncio.sleep(
                300
            )

            cutoff = (
                utc_now()
                - timedelta(
                    minutes=FILE_TTL_MINUTES
                )
            ).isoformat()

            with get_db() as db:

                old_jobs = db.execute(
                    """
                    SELECT
                        id,
                        output_path,
                        upload_id
                    FROM jobs
                    WHERE created_at < ?
                    """,
                    (cutoff,),
                ).fetchall()

                deleted_jobs = 0

                for job in old_jobs:

                    safe_unlink(
                        job["output_path"]
                    )

                    upload = db.execute(
                        """
                        SELECT path
                        FROM uploads
                        WHERE id = ?
                        """,
                        (job["upload_id"],),
                    ).fetchone()

                    if upload:

                        safe_unlink(
                            upload["path"]
                        )

                    db.execute(
                        """
                        DELETE FROM jobs
                        WHERE id = ?
                        """,
                        (job["id"],),
                    )

                    db.execute(
                        """
                        DELETE FROM uploads
                        WHERE id = ?
                        """,
                        (job["upload_id"],),
                    )

                    deleted_jobs += 1

                db.commit()

            # Also remove empty user folders.
            for directory in STORAGE_DIR.iterdir():

                if directory.is_dir():

                    try:

                        if not any(
                            directory.iterdir()
                        ):
                            directory.rmdir()

                    except OSError:
                        pass

            if deleted_jobs:
                logger.info(
                    "Cleanup removed %s old jobs.",
                    deleted_jobs,
                )

        except asyncio.CancelledError:

            break

        except Exception:

            logger.exception(
                "Cleanup failed."
            )


# ============================================================
# TELEGRAM KEYBOARD
# ============================================================

def conversion_keyboard(
    extension: str,
):

    builder = InlineKeyboardBuilder()

    for conversion_id, config in (
        CONVERSIONS.items()
    ):

        if extension in config[
            "extensions"
        ]:

            builder.button(
                text=config["title"],
                callback_data=(
                    f"convert:{conversion_id}"
                ),
            )

    builder.adjust(2)

    return builder.as_markup()


# ============================================================
# TELEGRAM /START
# ============================================================

@dp.message(
    CommandStart()
)
async def start_handler(
    message: Message,
):

    await message.answer(
        "👋 Привет!\n\n"
        "Я Universal File Converter Bot.\n\n"
        "📎 Отправь мне файл.\n"
        "После проверки я покажу доступные "
        "варианты конвертации.\n\n"
        f"📦 Максимальный размер: "
        f"{MAX_FILE_SIZE_MB} MB"
    )


# ============================================================
# TELEGRAM DOCUMENT
# ============================================================

@dp.message(
    F.document
)
async def document_handler(
    message: Message,
):

    if not message.from_user:
        return

    user_id = (
        message.from_user.id
    )

    if not check_rate_limit(
        user_id
    ):

        await message.answer(
            "⏳ Слишком много запросов.\n"
            "Попробуйте позже."
        )

        return

    document = message.document

    if not document.file_name:

        await message.answer(
            "❌ У файла отсутствует имя."
        )

        return

    filename = sanitize_filename(
        document.file_name
    )

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:

        await message.answer(
            "❌ Этот формат не поддерживается.\n\n"
            "Поддерживаемые форматы:\n"
            + ", ".join(
                sorted(
                    ALLOWED_EXTENSIONS
                )
            )
        )

        return

    telegram_size = (
        document.file_size or 0
    )

    if telegram_size > MAX_FILE_SIZE:

        await message.answer(
            f"❌ Файл слишком большой.\n"
            f"Максимум: {MAX_FILE_SIZE_MB} MB."
        )

        return

    status_message = (
        await message.answer(
            "⬇️ Загружаю файл..."
        )
    )

    path = create_upload_path(
        user_id,
        filename,
    )

    try:

        bot = message.bot

        telegram_file = (
            await bot.get_file(
                document.file_id
            )
        )

        await bot.download(
            telegram_file,
            destination=path,
        )

        # Actual file size check.
        ensure_file_size(
            path
        )

        # MIME + content.
        mime = validate_file_content(
            path,
            extension,
        )

        size = get_file_size(
            path
        )

        upload_id = str(
            uuid.uuid4()
        )

        await asyncio.to_thread(
            save_upload,
            upload_id,
            user_id,
            filename,
            path,
            extension,
            size,
        )

        user_last_upload[
            user_id
        ] = upload_id

        await status_message.edit_text(
            "✅ Файл проверен!\n\n"
            f"📄 {filename}\n"
            f"📦 {size / 1024 / 1024:.2f} MB\n"
            f"🔍 MIME: {mime}\n\n"
            "Выберите конвертацию:",
            reply_markup=conversion_keyboard(
                extension
            ),
        )

        logger.info(
            "File accepted: "
            "user=%s file=%s mime=%s",
            user_id,
            filename,
            mime,
        )

    except FileValidationError as exc:

        safe_unlink(
            path
        )

        await status_message.edit_text(
            "❌ Файл не прошёл проверку.\n\n"
            f"{exc}"
        )

    except Exception:

        safe_unlink(
            path
        )

        logger.exception(
            "Upload failed for user %s",
            user_id,
        )

        await status_message.edit_text(
            "❌ Не удалось загрузить файл."
        )


# ============================================================
# TELEGRAM CONVERSION
# ============================================================

@dp.callback_query(
    F.data.startswith("convert:")
)
async def conversion_callback(
    callback: CallbackQuery,
):

    if not callback.from_user:
        return

    user_id = (
        callback.from_user.id
    )

    if not check_rate_limit(
        user_id
    ):

        await callback.answer(
            "Слишком много запросов.",
            show_alert=True,
        )

        return

    conversion = (
        callback.data.split(
            ":",
            1,
        )[1]
    )

    if conversion not in CONVERSIONS:

        await callback.answer(
            "Неизвестная конвертация.",
            show_alert=True,
        )

        return

    upload_id = user_last_upload.get(
        user_id
    )

    if not upload_id:

        await callback.answer(
            "Файл устарел. "
            "Отправьте его снова.",
            show_alert=True,
        )

        return

    upload = await asyncio.to_thread(
        get_upload,
        upload_id,
    )

    if not upload:

        await callback.answer(
            "Файл не найден.",
            show_alert=True,
        )

        return

    path = Path(
        upload["path"]
    )

    if not path.exists():

        await callback.answer(
            "Файл больше не существует.",
            show_alert=True,
        )

        return

    extension = (
        upload["extension"]
        .lower()
    )

    config = CONVERSIONS[
        conversion
    ]

    if extension not in config[
        "extensions"
    ]:

        await callback.answer(
            "Эта конвертация "
            "недоступна для данного файла.",
            show_alert=True,
        )

        return

    job_id = str(
        uuid.uuid4()
    )

    await asyncio.to_thread(
        save_job,
        job_id,
        user_id,
        upload_id,
        conversion,
    )

    await job_queue.put(
        job_id
    )

    await callback.answer(
        "✅ Задача добавлена в очередь."
    )

    if callback.message:

        await callback.message.edit_text(
            "⏳ Файл добавлен в очередь.\n\n"
            f"🆔 Job: {job_id}\n"
            f"⚙️ {config['title']}\n\n"
            "Результат придёт автоматически."
        )

    logger.info(
        "Job queued: %s",
        job_id,
    )


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.error()
async def error_handler(
    event,
):

    logger.exception(
        "Unhandled Telegram error: %s",
        event.exception,
    )


# ============================================================
# GLOBAL BOT
# ============================================================

current_bot: Optional[Bot] = None


# ============================================================
# MAIN
# ============================================================

async def run_bot():

    global current_bot

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не установлен в .env"
        )

    init_database()

    current_bot = Bot(
        token=BOT_TOKEN
    )

    # Queue workers.
    worker_count = 3

    for worker_id in range(
        1,
        worker_count + 1,
    ):

        task = asyncio.create_task(
            worker(
                worker_id
            )
        )

        queue_workers.append(
            task
        )

    # Automatic cleanup.
    cleanup_task = asyncio.create_task(
        cleanup_old_files()
    )

    logger.info(
        "Bot started."
    )

    try:

        await dp.start_polling(
            current_bot,
            allowed_updates=(
                dp.resolve_used_update_types()
            ),
        )

    finally:

        shutdown_event.set()

        cleanup_task.cancel()

        for task in queue_workers:
            task.cancel()

        await asyncio.gather(
            *queue_workers,
            return_exceptions=True,
        )

        await asyncio.gather(
            cleanup_task,
            return_exceptions=True,
        )

        await current_bot.session.close()

        current_bot = None

        logger.info(
            "Bot stopped."
        )


# ============================================================
# TESTS
# ============================================================

class FileConverterTests(
    unittest.TestCase
):

    def test_sanitize_filename(
        self,
    ):

        result = sanitize_filename(
            "../../evil/test file?.txt"
        )

        self.assertNotIn(
            "/",
            result,
        )

        self.assertNotIn(
            "\\",
            result,
        )

    def test_detect_pdf(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            path = (
                Path(tmp)
                / "test.pdf"
            )

            path.write_bytes(
                b"%PDF-1.7\n"
            )

            self.assertEqual(
                detect_mime(path),
                "application/pdf",
            )

    def test_detect_png(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            path = (
                Path(tmp)
                / "test.png"
            )

            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
            )

            self.assertEqual(
                detect_mime(path),
                "image/png",
            )

    def test_json_format(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            directory = Path(tmp)

            source = (
                directory
                / "input.json"
            )

            target = (
                directory
                / "output.json"
            )

            source.write_text(
                '{"name":"Ali","age":20}',
                encoding="utf-8",
            )

            convert_json_format(
                source,
                target,
            )

            result = json.loads(
                target.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                result["name"],
                "Ali",
            )

    def test_json_minify(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            directory = Path(tmp)

            source = (
                directory
                / "input.json"
            )

            target = (
                directory
                / "output.json"
            )

            source.write_text(
                """
                {
                    "name": "Ali",
                    "age": 20
                }
                """,
                encoding="utf-8",
            )

            convert_json_minify(
                source,
                target,
            )

            result = (
                target.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                result,
                '{"name":"Ali","age":20}',
            )

    def test_csv_json(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            directory = Path(tmp)

            source = (
                directory
                / "input.csv"
            )

            target = (
                directory
                / "output.json"
            )

            source.write_text(
                "name,age\nAli,20\nBob,25\n",
                encoding="utf-8",
            )

            convert_csv_to_json(
                source,
                target,
            )

            result = json.loads(
                target.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                len(result),
                2,
            )

            self.assertEqual(
                result[0]["name"],
                "Ali",
            )

    def test_zip(
        self,
    ):

        with tempfile.TemporaryDirectory() as tmp:

            directory = Path(tmp)

            source = (
                directory
                / "test.txt"
            )

            target = (
                directory
                / "test.zip"
            )

            source.write_text(
                "hello",
                encoding="utf-8",
            )

            convert_to_zip(
                source,
                target,
            )

            self.assertTrue(
                target.exists()
            )

            with zipfile.ZipFile(
                target,
                "r",
            ) as archive:

                self.assertIn(
                    "test.txt",
                    archive.namelist(),
                )


def run_tests():

    import unittest

    unittest.main(
        argv=[
            "file_converter_bot.py",
        ],
        verbosity=2,
    )


# ============================================================
# ENTRYPOINT
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run tests.",
    )

    args = parser.parse_args()

    if args.test:

        run_tests()

    else:

        asyncio.run(
            run_bot()
        )


if __name__ == "__main__":
    main()
