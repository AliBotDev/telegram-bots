# 📁 Universal File Converter Bot

A free and open-source Telegram bot for converting files directly inside Telegram.

The project is designed to be simple to run locally while providing useful security and file-processing features.

## ✨ Features

* 📄 PDF → TXT
* 🖼️ Images → JPG
* 🖼️ Images → WebP
* 🧩 JSON formatting
* ⚡ JSON minification
* 📊 CSV → JSON
* 📦 Files → ZIP
* 📏 File size limits
* 🔍 MIME / file signature validation
* 🛡️ File content validation
* 🚦 Rate limiting
* ⚙️ Async processing queue
* 🗃️ SQLite job tracking
* 🧹 Automatic file cleanup
* 🔐 Filename sanitization
* 🧪 Built-in tests
* 💰 No paid APIs required

## 📦 Supported Formats

### Documents

* PDF
* TXT
* Markdown
* JSON
* CSV

### Images

* JPG
* JPEG
* PNG
* WEBP
* BMP
* GIF

## 🛡️ Security

The bot does not blindly trust the file extension.

Uploaded files are checked using:

* file signatures
* MIME detection
* actual file contents
* format-specific parsers
* file size validation
* filename sanitization

For example, renaming a PDF to `image.jpg` will not make it pass image validation.

The bot also protects against path traversal when processing filenames.

## ⚙️ Requirements

* Python 3.12+
* Telegram Bot Token

No PostgreSQL, Redis, Docker or paid API is required for the local version.

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/AliBotDev/telegram-bots.git
cd telegram-bots/Universal-File-Converter
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## 🔑 Configuration

Create a `.env` file in
