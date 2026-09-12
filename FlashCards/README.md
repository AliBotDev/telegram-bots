# 🧠 Flashcards Bot

A Telegram bot for learning foreign-language vocabulary using **flashcards** and **spaced repetition**.

The bot provides automatic language decks, level-based vocabulary, custom decks, study statistics, and an offline built-in multilingual vocabulary database.

## ✨ Features

* 🧠 Flashcards with spaced repetition
* 📚 Automatic language decks
* 🎯 CEFR levels **A1–C1**
* 🇯🇵 JLPT levels **N5–N1** for Japanese
* 🌍 Multilingual vocabulary
* 🔄 Automatic translation updates for existing cards
* 📊 Learning statistics
* 🗂 Custom decks
* ➕ Add your own cards
* 💾 SQLite database
* 🧪 Built-in unit tests
* 🔧 Automatic database migration
* ⚡ Asynchronous Telegram bot powered by `aiogram`

## 🌍 Supported Languages

### 🇬🇧 English

A1, A2, B1, B2, C1

### 🇩🇪 German

A1, A2, B1, B2, C1

### 🇪🇸 Spanish

A1, A2, B1, B2, C1

### 🇫🇷 French

A1, A2, B1, B2, C1

### 🇯🇵 Japanese

N5, N4, N3, N2, N1

### 🇷🇺 Russian

A1, A2, B1, B2, C1

There are **30 automatic study decks** in total.

## 🔤 Translation System

The built-in vocabulary contains translations for six languages:

* English
* German
* Spanish
* French
* Japanese
* Russian

### English

When studying English, the bot provides:

```text
English → German + Spanish + French + Japanese + Russian
```

Example:

```text
🇬🇧 hello

🇩🇪 hallo
🇪🇸 hola
🇫🇷 bonjour
🇯🇵 こんにちは
🇷🇺 привет
```

### Russian

When studying Russian, the bot provides:

```text
Russian → English + German + Spanish + French + Japanese
```

Example:

```text
🇷🇺 привет

🇬🇧 hello
🇩🇪 hallo
🇪🇸 hola
🇫🇷 bonjour
🇯🇵 こんにちは
```

### Other languages

For German, Spanish, French, and Japanese:

```text
Language → English + Russian
```

## 🛠 Tech Stack

This project uses:

* Python 3.10+
* [aiogram](https://github.com/aiogram/aiogram)
* SQLite
* python-dotenv
* asyncio
* unittest

## 📁 Project Structure

```text
flashcards-bot/
│
├── flash_cards_bot.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

The SQLite database is created automatically:

```text
flashcards.db
```

It is recommended to keep the database out of version control.

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Create a virtual environment:

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 📦 requirements.txt

The project requires:

```text
aiogram
python-dotenv
```

You can install them manually with:

```bash
pip install aiogram python-dotenv
```

## 🔑 Telegram Bot Configuration

Create a Telegram bot using **@BotFather** and obtain your bot token.

Create a `.env` file in the project root:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
DB_PATH=flashcards.db
MAX_DECKS_PER_USER=100
MAX_CARDS_PER_DECK=5000
SESSION_TIMEOUT_MINUTES=60
```

Example:

```env
BOT_TOKEN=1234567890:AAExampleToken
DB_PATH=flashcards.db
MAX_DECKS_PER_USER=100
MAX_CARDS_PER_DECK=5000
SESSION_TIMEOUT_MINUTES=60
```

**Never commit your `.env` file or bot token to GitHub.**

## ▶️ Running the Bot

Start the bot with:

```bash
python flash_cards_bot.py
```

On startup, the bot initializes and migrates the database automatically.

You should see log messages similar to:

```text
Database initialized.
Database migration completed successfully.
Flashcards bot started.
```

## 🧪 Running Tests

The project includes built-in unit tests.

Run:

```bash
python flash_cards_bot.py --test
```

The tests check:

* vocabulary structure
* supported languages
* language levels
* English decks
* Russian decks
* Japanese levels
* cumulative decks
* deck parsing
* automatic deck count
* translation structure
* spaced repetition calculations

## 📚 Commands

### `/start`

Displays the welcome message and supported languages.

```text
/start
```

### `/help`

Displays all available commands.

```text
/help
```

### `/learn`

Displays all automatic study decks.

```text
/learn
```

You can also directly start a deck:

```text
/learn English A1
```

```text
/learn Russian A1
```

Other examples:

```text
/learn German B1
/learn Spanish B2
/learn French C1
/learn Japanese N3
```

## 🗂 Custom Decks

Create your own deck:

```text
/deck My Words
```

Add a card:

```text
/add My Words | hello | привет
```

Start studying:

```text
/study My Words
```

## 📋 View Your Decks

Use:

```text
/decks
```

The bot displays:

* deck name
* number of cards
* number of cards currently due

## 📊 Statistics

Use:

```text
/stats
```

The bot displays:

```text
📚 Decks
🃏 Cards
⏰ Cards due
🔄 Reviews
🎯 Correct answers
📈 Accuracy
```

Example:

```text
📊 Statistics

📚 Decks: 3
🃏 Cards: 180
⏰ Due: 12
🔄 Reviews: 245
🎯 Correct: 201
📈 Accuracy: 82.0%
```

## 🧠 Spaced Repetition

The bot uses a spaced-repetition system to schedule future reviews.

After viewing a card, the user selects one of four ratings:

```text
🔴 Again
🟠 Hard
🟢 Good
🔵 Easy
```

The next review interval is calculated based on the selected rating and the card's previous history.

Typical first intervals include:

```text
Again → about 10 minutes
Good  → 1 day
Good  → 6 days
Easy  → longer interval
```

The interval grows as the card is successfully reviewed.

The maximum interval is limited to **3650 days**.

## 💾 Database

The bot uses SQLite for persistent storage.

The main tables are:

```text
decks
cards
reviews
```

### `decks`

Stores user-created and automatic decks.

### `cards`

Stores:

* front side of the card
* back side
* English translation
* German translation
* Spanish translation
* French translation
* Japanese translation
* Russian translation
* next review date
* review interval
* ease factor
* repetitions
* lapses
* total reviews
* correct reviews

### `reviews`

Stores review history, including:

* card ID
* user ID
* rating
* previous interval
* new interval
* review timestamp

## 🔄 Database Migration

The bot automatically checks the existing database structure during startup.

When an older database is detected, missing translation columns are added automatically.

This allows the bot to upgrade an existing `flashcards.db` without requiring the database to be deleted.

## 🔐 Security

Do not commit secrets or private runtime data to GitHub.

Recommended `.gitignore`:

```gitignore
.env
*.db
__pycache__/
*.pyc
venv/
.venv/
.idea/
.vscode/
```

This prevents files such as these from being committed:

```text
.env
flashcards.db
__pycache__/
```

## 🌳 Git Setup

Initialize Git:

```bash
git init
```

Add the project files:

```bash
git add .
```

Create the first commit:

```bash
git commit -m "Initial commit"
```

Add your GitHub repository:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
```

Set the main branch:

```bash
git branch -M main
```

Push the project:

```bash
git push -u origin main
```

## 📝 Example Workflow

Start the bot:

```text
/start
```

Choose:

```text
/learn
```

Select:

```text
🇬🇧 English A1
```

The bot shows:

```text
❓ hello
```

Reveal the answer:

```text
🇩🇪 hallo
🇪🇸 hola
🇫🇷 bonjour
🇯🇵 こんにちは
🇷🇺 привет
```

Then select:

```text
🔴 Again
🟠 Hard
🟢 Good
🔵 Easy
```

The bot schedules the next review automatically.

## 📌 Current Limitations

The built-in vocabulary is stored directly in the Python source code as an offline dataset.

Custom cards created with:

```text
/add Deck | front | back
```

currently use the provided `front` and `back` values rather than automatically generating translations.

## 🚧 Future Improvements

Possible future additions include:

* 🌐 User interface localization
* 🔊 Text-to-speech pronunciation
* 🎧 Audio exercises
* 📝 Multiple-choice questions
* ✍️ Typing exercises
* 📈 Advanced progress charts
* 🏆 Learning streaks
* 👤 User profiles
* ☁️ PostgreSQL support
* 🤖 AI-generated vocabulary
* 🧩 More languages
* 📱 Better Telegram UI

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome.

To contribute:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Create a new branch:

```bash
git checkout -b feature/my-feature
```

Make your changes, run the tests:

```bash
python flash_cards_bot.py --test
```

Then commit and push your changes.

## 📄 License

This project is licensed under the terms specified in the `LICENSE` file.

## ⭐ Support

If you find this project useful, consider giving the repository a ⭐ on GitHub.

---

Made with ❤️ and Python.

```
```
