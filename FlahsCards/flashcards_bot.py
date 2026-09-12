import argparse
import asyncio
import html
import logging
import os
import sqlite3
import unittest
import uuid

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

DB_PATH = Path(
    os.getenv(
        "DB_PATH",
        "flashcards.db",
    )
)

MAX_DECKS_PER_USER = int(
    os.getenv(
        "MAX_DECKS_PER_USER",
        "100",
    )
)

MAX_CARDS_PER_DECK = int(
    os.getenv(
        "MAX_CARDS_PER_DECK",
        "5000",
    )
)

SESSION_TIMEOUT_MINUTES = int(
    os.getenv(
        "SESSION_TIMEOUT_MINUTES",
        "60",
    )
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "flashcards_bot"
)


# ============================================================
# TELEGRAM
# ============================================================

dp = Dispatcher()

current_bot: Optional[Bot] = None

shutdown_event = asyncio.Event()

db_lock = asyncio.Lock()

study_sessions: Dict[str, dict] = {}


# ============================================================
# MULTILINGUAL VOCABULARY
# ============================================================
#
# Every entry:
#
# (
#     CEFR level,
#     JLPT level,
#     English,
#     German,
#     Spanish,
#     French,
#     Japanese,
#     Russian
# )
#
# Higher levels are cumulative.
# Japanese uses JLPT.
# Russian uses CEFR.
# ============================================================

VOCABULARY = [

    # ========================================================
    # A1 / N5
    # ========================================================

    ("A1", "N5", "hello", "hallo", "hola", "bonjour", "こんにちは", "привет"),
    ("A1", "N5", "goodbye", "tschüss", "adiós", "au revoir", "さようなら", "до свидания"),
    ("A1", "N5", "please", "bitte", "por favor", "s'il vous plaît", "おねがいします", "пожалуйста"),
    ("A1", "N5", "thank you", "danke", "gracias", "merci", "ありがとう", "спасибо"),
    ("A1", "N5", "yes", "ja", "sí", "oui", "はい", "да"),
    ("A1", "N5", "no", "nein", "no", "non", "いいえ", "нет"),
    ("A1", "N5", "water", "Wasser", "agua", "eau", "みず", "вода"),
    ("A1", "N5", "food", "Essen", "comida", "nourriture", "たべもの", "еда"),
    ("A1", "N5", "bread", "Brot", "pan", "pain", "パン", "хлеб"),
    ("A1", "N5", "milk", "Milch", "leche", "lait", "ミルク", "молоко"),
    ("A1", "N5", "house", "Haus", "casa", "maison", "いえ", "дом"),
    ("A1", "N5", "room", "Zimmer", "habitación", "chambre", "へや", "комната"),
    ("A1", "N5", "school", "Schule", "escuela", "école", "がっこう", "школа"),
    ("A1", "N5", "teacher", "Lehrer", "profesor", "professeur", "せんせい", "учитель"),
    ("A1", "N5", "student", "Schüler", "estudiante", "étudiant", "がくせい", "ученик / студент"),
    ("A1", "N5", "friend", "Freund", "amigo", "ami", "ともだち", "друг"),
    ("A1", "N5", "family", "Familie", "familia", "famille", "かぞく", "семья"),
    ("A1", "N5", "mother", "Mutter", "madre", "mère", "おかあさん", "мать / мама"),
    ("A1", "N5", "father", "Vater", "padre", "père", "おとうさん", "отец / папа"),
    ("A1", "N5", "brother", "Bruder", "hermano", "frère", "おにいさん", "брат"),
    ("A1", "N5", "sister", "Schwester", "hermana", "sœur", "おねえさん", "сестра"),
    ("A1", "N5", "book", "Buch", "libro", "livre", "ほん", "книга"),
    ("A1", "N5", "pen", "Stift", "bolígrafo", "stylo", "ペン", "ручка"),
    ("A1", "N5", "table", "Tisch", "mesa", "table", "つくえ", "стол"),
    ("A1", "N5", "chair", "Stuhl", "silla", "chaise", "いす", "стул"),
    ("A1", "N5", "door", "Tür", "puerta", "porte", "ドア", "дверь"),
    ("A1", "N5", "window", "Fenster", "ventana", "fenêtre", "まど", "окно"),
    ("A1", "N5", "phone", "Telefon", "teléfono", "téléphone", "でんわ", "телефон"),
    ("A1", "N5", "computer", "Computer", "ordenador", "ordinateur", "コンピューター", "компьютер"),
    ("A1", "N5", "car", "Auto", "coche", "voiture", "くるま", "машина"),
    ("A1", "N5", "bus", "Bus", "autobús", "bus", "バス", "автобус"),
    ("A1", "N5", "train", "Zug", "tren", "train", "でんしゃ", "поезд"),
    ("A1", "N5", "city", "Stadt", "ciudad", "ville", "まち", "город"),
    ("A1", "N5", "street", "Straße", "calle", "rue", "みち", "улица"),
    ("A1", "N5", "shop", "Geschäft", "tienda", "magasin", "みせ", "магазин"),
    ("A1", "N5", "today", "heute", "hoy", "aujourd'hui", "きょう", "сегодня"),
    ("A1", "N5", "tomorrow", "morgen", "mañana", "demain", "あした", "завтра"),
    ("A1", "N5", "yesterday", "gestern", "ayer", "hier", "きのう", "вчера"),
    ("A1", "N5", "morning", "Morgen", "mañana", "matin", "あさ", "утро"),
    ("A1", "N5", "evening", "Abend", "tarde", "soir", "ゆうがた", "вечер"),
    ("A1", "N5", "night", "Nacht", "noche", "nuit", "よる", "ночь"),
    ("A1", "N5", "big", "groß", "grande", "grand", "おおきい", "большой"),
    ("A1", "N5", "small", "klein", "pequeño", "petit", "ちいさい", "маленький"),
    ("A1", "N5", "good", "gut", "bueno", "bon", "いい", "хороший"),
    ("A1", "N5", "bad", "schlecht", "malo", "mauvais", "わるい", "плохой"),
    ("A1", "N5", "happy", "glücklich", "feliz", "heureux", "しあわせ", "счастливый"),
    ("A1", "N5", "sad", "traurig", "triste", "triste", "かなしい", "грустный"),
    ("A1", "N5", "go", "gehen", "ir", "aller", "いく", "идти"),
    ("A1", "N5", "come", "kommen", "venir", "venir", "くる", "приходить"),
    ("A1", "N5", "eat", "essen", "comer", "manger", "たべる", "есть"),
    ("A1", "N5", "drink", "trinken", "beber", "boire", "のむ", "пить"),
    ("A1", "N5", "sleep", "schlafen", "dormir", "dormir", "ねる", "спать"),
    ("A1", "N5", "wake up", "aufwachen", "despertarse", "se réveiller", "おきる", "просыпаться"),
    ("A1", "N5", "see", "sehen", "ver", "voir", "みる", "видеть"),
    ("A1", "N5", "read", "lesen", "leer", "lire", "よむ", "читать"),
    ("A1", "N5", "write", "schreiben", "escribir", "écrire", "かく", "писать"),
    ("A1", "N5", "listen", "zuhören", "escuchar", "écouter", "きく", "слушать"),
    ("A1", "N5", "speak", "sprechen", "hablar", "parler", "はなす", "говорить"),
    ("A1", "N5", "learn", "lernen", "aprender", "apprendre", "まなぶ", "учиться / изучать"),
    ("A1", "N5", "work", "arbeiten", "trabajar", "travailler", "はたらく", "работать"),
    ("A1", "N5", "play", "spielen", "jugar", "jouer", "あそぶ", "играть"),

    # ========================================================
    # A2 / N4
    # ========================================================

    ("A2", "N4", "usually", "normalerweise", "normalmente", "habituellement", "ふつうは", "обычно"),
    ("A2", "N4", "sometimes", "manchmal", "a veces", "parfois", "ときどき", "иногда"),
    ("A2", "N4", "always", "immer", "siempre", "toujours", "いつも", "всегда"),
    ("A2", "N4", "never", "nie", "nunca", "jamais", "けっして", "никогда"),
    ("A2", "N4", "often", "oft", "a menudo", "souvent", "よく", "часто"),
    ("A2", "N4", "early", "früh", "temprano", "tôt", "はやく", "рано"),
    ("A2", "N4", "late", "spät", "tarde", "tard", "おそく", "поздно"),
    ("A2", "N4", "healthy", "gesund", "saludable", "sain", "けんこうてき", "здоровый"),
    ("A2", "N4", "dangerous", "gefährlich", "peligroso", "dangereux", "きけん", "опасный"),
    ("A2", "N4", "careful", "vorsichtig", "cuidadoso", "prudent", "ちゅういぶかい", "осторожный"),
    ("A2", "N4", "enough", "genug", "suficiente", "assez", "じゅうぶん", "достаточно"),
    ("A2", "N4", "already", "schon", "ya", "déjà", "もう", "уже"),
    ("A2", "N4", "still", "noch", "todavía", "encore", "まだ", "всё ещё"),
    ("A2", "N4", "before", "vorher", "antes", "avant", "まえに", "до / раньше"),
    ("A2", "N4", "after", "nachher", "después", "après", "あとで", "после / потом"),
    ("A2", "N4", "during", "während", "durante", "pendant", "あいだ", "во время"),
    ("A2", "N4", "because", "weil", "porque", "parce que", "なぜなら", "потому что"),
    ("A2", "N4", "different", "verschieden", "diferente", "différent", "ちがう", "разный"),
    ("A2", "N4", "important", "wichtig", "importante", "important", "たいせつ", "важный"),
    ("A2", "N4", "possible", "möglich", "posible", "possible", "かのう", "возможный"),
    ("A2", "N4", "together", "zusammen", "juntos", "ensemble", "いっしょに", "вместе"),
    ("A2", "N4", "choose", "wählen", "elegir", "choisir", "えらぶ", "выбирать"),
    ("A2", "N4", "decide", "entscheiden", "decidir", "décider", "きめる", "решать"),
    ("A2", "N4", "remember", "sich erinnern", "recordar", "se souvenir", "おぼえる", "помнить"),
    ("A2", "N4", "forget", "vergessen", "olvidar", "oublier", "わすれる", "забывать"),
    ("A2", "N4", "explain", "erklären", "explicar", "expliquer", "せつめいする", "объяснять"),
    ("A2", "N4", "invite", "einladen", "invitar", "inviter", "しょうたいする", "приглашать"),
    ("A2", "N4", "arrive", "ankommen", "llegar", "arriver", "つく", "прибывать"),
    ("A2", "N4", "leave", "verlassen", "salir", "partir", "でる", "уходить"),
    ("A2", "N4", "borrow", "ausleihen", "pedir prestado", "emprunter", "かりる", "брать взаймы"),
    ("A2", "N4", "lend", "leihen", "prestar", "prêter", "かす", "давать взаймы"),
    ("A2", "N4", "return", "zurückgeben", "devolver", "rendre", "かえす", "возвращать"),
    ("A2", "N4", "prepare", "vorbereiten", "preparar", "préparer", "じゅんびする", "готовить"),
    ("A2", "N4", "repair", "reparieren", "reparar", "réparer", "なおす", "ремонтировать"),
    ("A2", "N4", "imagine", "sich vorstellen", "imaginar", "imaginer", "そうぞうする", "представлять"),
    ("A2", "N4", "promise", "versprechen", "prometer", "promettre", "やくそくする", "обещать"),
    ("A2", "N4", "hope", "hoffen", "esperar", "espérer", "きたいする", "надеяться"),
    ("A2", "N4", "worry", "sich sorgen", "preocuparse", "s'inquiéter", "しんぱいする", "волноваться"),
    ("A2", "N4", "agree", "zustimmen", "estar de acuerdo", "être d'accord", "さんせいする", "соглашаться"),
    ("A2", "N4", "disagree", "nicht zustimmen", "no estar de acuerdo", "ne pas être d'accord", "はんたいする", "не соглашаться"),
    ("A2", "N4", "happen", "passieren", "suceder", "se passer", "おこる", "происходить"),
    ("A2", "N4", "become", "werden", "convertirse", "devenir", "なる", "становиться"),
    ("A2", "N4", "continue", "fortsetzen", "continuar", "continuer", "つづける", "продолжать"),
    ("A2", "N4", "finish", "beenden", "terminar", "finir", "おわる", "заканчивать"),
    ("A2", "N4", "carry", "tragen", "llevar", "porter", "もつ", "нести"),
    ("A2", "N4", "wear", "tragen", "llevar", "porter", "きる", "носить"),
    ("A2", "N4", "weather", "Wetter", "tiempo", "météo", "てんき", "погода"),
    ("A2", "N4", "journey", "Reise", "viaje", "voyage", "りょこう", "путешествие"),
    ("A2", "N4", "cheap", "billig", "barato", "bon marché", "やすい", "дешёвый"),
    ("A2", "N4", "expensive", "teuer", "caro", "cher", "たかい", "дорогой"),
    ("A2", "N4", "reason", "Grund", "razón", "raison", "りゆう", "причина"),
    ("A2", "N4", "problem", "Problem", "problema", "problème", "もんだい", "проблема"),
    ("A2", "N4", "answer", "Antwort", "respuesta", "réponse", "こたえ", "ответ"),
    ("A2", "N4", "question", "Frage", "pregunta", "question", "しつもん", "вопрос"),
    ("A2", "N4", "practice", "Übung", "práctica", "pratique", "れんしゅう", "практика"),
    ("A2", "N4", "hobby", "Hobby", "afición", "loisir", "しゅみ", "хобби"),
    ("A2", "N4", "travel", "reisen", "viajar", "voyager", "りょこうする", "путешествовать"),
    ("A2", "N4", "useful", "nützlich", "útil", "utile", "やくにたつ", "полезный"),
    ("A2", "N4", "convenient", "bequem", "cómodo", "pratique", "べんり", "удобный"),

    # ========================================================
    # B1 / N3
    # ========================================================

    ("B1", "N3", "experience", "Erfahrung", "experiencia", "expérience", "けいけん", "опыт"),
    ("B1", "N3", "opportunity", "Möglichkeit", "oportunidad", "opportunité", "きかい", "возможность"),
    ("B1", "N3", "environment", "Umwelt", "medio ambiente", "environnement", "かんきょう", "окружающая среда"),
    ("B1", "N3", "relationship", "Beziehung", "relación", "relation", "かんけい", "отношения / связь"),
    ("B1", "N3", "decision", "Entscheidung", "decisión", "décision", "けってい", "решение"),
    ("B1", "N3", "improve", "verbessern", "mejorar", "améliorer", "かいぜんする", "улучшать"),
    ("B1", "N3", "achieve", "erreichen", "lograr", "atteindre", "たっせいする", "достигать"),
    ("B1", "N3", "avoid", "vermeiden", "evitar", "éviter", "さける", "избегать"),
    ("B1", "N3", "depend", "abhängen", "depender", "dépendre", "いぞんする", "зависеть"),
    ("B1", "N3", "suggest", "vorschlagen", "sugerir", "suggérer", "ていあんする", "предлагать"),
    ("B1", "N3", "provide", "bereitstellen", "proporcionar", "fournir", "ていきょうする", "предоставлять"),
    ("B1", "N3", "compare", "vergleichen", "comparar", "comparer", "くらべる", "сравнивать"),
    ("B1", "N3", "increase", "erhöhen", "aumentar", "augmenter", "ふやす", "увеличивать"),
    ("B1", "N3", "reduce", "reduzieren", "reducir", "réduire", "へらす", "уменьшать"),
    ("B1", "N3", "behavior", "Verhalten", "comportamiento", "comportement", "こうどう", "поведение"),
    ("B1", "N3", "develop", "entwickeln", "desarrollar", "développer", "はってんさせる", "развивать"),
    ("B1", "N3", "discover", "entdecken", "descubrir", "découvrir", "はっけんする", "обнаруживать"),
    ("B1", "N3", "describe", "beschreiben", "describir", "décrire", "せつめいする", "описывать"),
    ("B1", "N3", "encourage", "ermutigen", "animar", "encourager", "はげます", "поощрять"),
    ("B1", "N3", "require", "fordern", "requerir", "exiger", "ひつようとする", "требовать"),
    ("B1", "N3", "consider", "berücksichtigen", "considerar", "considérer", "こうりょする", "учитывать"),
    ("B1", "N3", "notice", "bemerken", "notar", "remarquer", "きづく", "замечать"),
    ("B1", "N3", "prefer", "bevorzugen", "preferir", "préférer", "このむ", "предпочитать"),
    ("B1", "N3", "realize", "erkennen", "darse cuenta", "se rendre compte", "きづく", "осознавать"),
    ("B1", "N3", "advantage", "Vorteil", "ventaja", "avantage", "りてん", "преимущество"),
    ("B1", "N3", "disadvantage", "Nachteil", "desventaja", "inconvénient", "けってん", "недостаток"),
    ("B1", "N3", "challenge", "Herausforderung", "desafío", "défi", "ちょうせん", "вызов / сложность"),
    ("B1", "N3", "choice", "Wahl", "elección", "choix", "せんたく", "выбор"),
    ("B1", "N3", "confidence", "Vertrauen", "confianza", "confiance", "じしん", "уверенность"),
    ("B1", "N3", "knowledge", "Kenntnis", "conocimiento", "connaissance", "ちしき", "знания"),
    ("B1", "N3", "skill", "Fähigkeit", "habilidad", "compétence", "のうりょく", "навык"),
    ("B1", "N3", "solution", "Lösung", "solución", "solution", "かいけつ", "решение"),
    ("B1", "N3", "purpose", "Zweck", "propósito", "objectif", "もくてき", "цель"),
    ("B1", "N3", "result", "Ergebnis", "resultado", "résultat", "けっか", "результат"),
    ("B1", "N3", "research", "Forschung", "investigación", "recherche", "けんきゅう", "исследование"),
    ("B1", "N3", "community", "Gemeinschaft", "comunidad", "communauté", "ちいき", "сообщество"),
    ("B1", "N3", "society", "Gesellschaft", "sociedad", "société", "しゃかい", "общество"),
    ("B1", "N3", "likely", "wahrscheinlich", "probable", "probable", "かのうせいがたかい", "вероятный"),
    ("B1", "N3", "unlikely", "unwahrscheinlich", "improbable", "improbable", "かのうせいがひくい", "маловероятный"),
    ("B1", "N3", "although", "obwohl", "aunque", "bien que", "けれども", "хотя"),
    ("B1", "N3", "however", "allerdings", "sin embargo", "cependant", "しかし", "однако"),
    ("B1", "N3", "instead", "stattdessen", "en lugar de", "au lieu de", "かわりに", "вместо этого"),
    ("B1", "N3", "perhaps", "vielleicht", "quizás", "peut-être", "たぶん", "возможно"),
    ("B1", "N3", "probably", "wahrscheinlich", "probablemente", "probablement", "おそらく", "вероятно"),
    ("B1", "N3", "especially", "besonders", "especialmente", "surtout", "とくに", "особенно"),
    ("B1", "N3", "actually", "tatsächlich", "en realidad", "en fait", "じっさいに", "на самом деле"),
    ("B1", "N3", "eventually", "schließlich", "finalmente", "finalement", "けっきょく", "в конечном итоге"),
    ("B1", "N3", "recently", "kürzlich", "recientemente", "récemment", "さいきん", "недавно"),
    ("B1", "N3", "success", "Erfolg", "éxito", "succès", "せいこう", "успех"),
    ("B1", "N3", "failure", "Misserfolg", "fracaso", "échec", "しっぱい", "неудача"),
    ("B1", "N3", "habit", "Gewohnheit", "hábito", "habitude", "しゅうかん", "привычка"),
    ("B1", "N3", "goal", "Ziel", "meta", "but", "もくひょう", "цель"),
    ("B1", "N3", "plan", "Plan", "plan", "plan", "けいかく", "план"),
    ("B1", "N3", "future", "Zukunft", "futuro", "avenir", "しょうらい", "будущее"),
    ("B1", "N3", "past", "Vergangenheit", "pasado", "passé", "かこ", "прошлое"),
    ("B1", "N3", "present", "Gegenwart", "presente", "présent", "げんざい", "настоящее"),
    ("B1", "N3", "culture", "Kultur", "cultura", "culture", "ぶんか", "культура"),

    # ========================================================
    # B2 / N2
    # ========================================================

    ("B2", "N2", "approximately", "ungefähr", "aproximadamente", "environ", "およそ", "приблизительно"),
    ("B2", "N2", "significant", "bedeutend", "significativo", "significatif", "じゅうような", "значительный"),
    ("B2", "N2", "consequence", "Folge", "consecuencia", "conséquence", "けっか", "последствие"),
    ("B2", "N2", "requirement", "Anforderung", "requisito", "exigence", "ようけん", "требование"),
    ("B2", "N2", "assumption", "Annahme", "suposición", "hypothèse", "かてい", "предположение"),
    ("B2", "N2", "reliable", "zuverlässig", "fiable", "fiable", "しんらいできる", "надёжный"),
    ("B2", "N2", "efficient", "effizient", "eficiente", "efficace", "こうりつてき", "эффективный"),
    ("B2", "N2", "controversial", "umstritten", "controvertido", "controversé", "ぎろんをよぶ", "спорный"),
    ("B2", "N2", "perspective", "Perspektive", "perspectiva", "perspective", "してん", "точка зрения"),
    ("B2", "N2", "circumstance", "Umstand", "circunstancia", "circonstance", "じょうきょう", "обстоятельство"),
    ("B2", "N2", "implement", "umsetzen", "implementar", "mettre en œuvre", "じっこうする", "реализовывать"),
    ("B2", "N2", "establish", "festlegen", "establecer", "établir", "せっていする", "устанавливать"),
    ("B2", "N2", "maintain", "aufrechterhalten", "mantener", "maintenir", "いじする", "поддерживать"),
    ("B2", "N2", "evaluate", "bewerten", "evaluar", "évaluer", "ひょうかする", "оценивать"),
    ("B2", "N2", "nevertheless", "dennoch", "sin embargo", "néanmoins", "それにもかかわらず", "тем не менее"),
    ("B2", "N2", "substantial", "wesentlich", "sustancial", "substantiel", "かなりの", "существенный"),
    ("B2", "N2", "consumption", "Verbrauch", "consumo", "consommation", "しょうひ", "потребление"),
    ("B2", "N2", "sustainable", "nachhaltig", "sostenible", "durable", "じぞくかのう", "устойчивый"),
    ("B2", "N2", "influence", "Einfluss", "influencia", "influence", "えいきょう", "влияние"),
    ("B2", "N2", "accurate", "genau", "preciso", "précis", "せいかく", "точный"),
    ("B2", "N2", "complex", "komplex", "complejo", "complexe", "ふくざつ", "сложный"),
    ("B2", "N2", "decline", "Rückgang", "declive", "déclin", "げんしょう", "снижение"),
    ("B2", "N2", "expand", "erweitern", "ampliar", "élargir", "かくだいする", "расширять"),
    ("B2", "N2", "generate", "erzeugen", "generar", "générer", "うみだす", "создавать"),
    ("B2", "N2", "highlight", "hervorheben", "destacar", "souligner", "きょうちょうする", "подчёркивать"),
    ("B2", "N2", "identify", "identifizieren", "identificar", "identifier", "かくにんする", "выявлять"),
    ("B2", "N2", "indicate", "andeuten", "indicar", "indiquer", "しめす", "указывать"),
    ("B2", "N2", "interpret", "interpretieren", "interpretar", "interpréter", "かいしゃくする", "интерпретировать"),
    ("B2", "N2", "obtain", "erhalten", "obtener", "obtenir", "えられる", "получать"),
    ("B2", "N2", "participate", "teilnehmen", "participar", "participer", "さんかする", "участвовать"),
    ("B2", "N2", "perceive", "wahrnehmen", "percibir", "percevoir", "にんしきする", "воспринимать"),
    ("B2", "N2", "predict", "vorhersagen", "predecir", "prévoir", "よそくする", "предсказывать"),
    ("B2", "N2", "promote", "fördern", "promover", "favoriser", "そくしんする", "способствовать / продвигать"),
    ("B2", "N2", "represent", "darstellen", "representar", "représenter", "あらわす", "представлять"),
    ("B2", "N2", "retain", "beibehalten", "conservar", "conserver", "たもつ", "сохранять"),
    ("B2", "N2", "shift", "Verschiebung", "cambio", "changement", "へんか", "сдвиг / изменение"),
    ("B2", "N2", "stable", "stabil", "estable", "stable", "あんていした", "стабильный"),
    ("B2", "N2", "tendency", "Tendenz", "tendencia", "tendance", "けいこう", "тенденция"),
    ("B2", "N2", "valid", "gültig", "válido", "valide", "ゆうこう", "действительный"),
    ("B2", "N2", "whereas", "während", "mientras que", "tandis que", "いっぽう", "тогда как"),
    ("B2", "N2", "despite", "trotz", "a pesar de", "malgré", "にもかかわらず", "несмотря на"),
    ("B2", "N2", "therefore", "deshalb", "por lo tanto", "donc", "したがって", "следовательно"),
    ("B2", "N2", "otherwise", "andernfalls", "de lo contrario", "sinon", "さもなければ", "в противном случае"),
    ("B2", "N2", "considerably", "erheblich", "considerablemente", "considérablement", "かなり", "значительно"),
    ("B2", "N2", "frequently", "häufig", "frecuentemente", "fréquemment", "ひんぱんに", "часто"),
    ("B2", "N2", "primarily", "hauptsächlich", "principalmente", "principalement", "おもに", "главным образом"),
    ("B2", "N2", "relatively", "relativ", "relativamente", "relativement", "ひかくてき", "относительно"),
    ("B2", "N2", "ultimately", "letztlich", "en última instancia", "en fin de compte", "けっきょく", "в конечном счёте"),
    ("B2", "N2", "adequate", "angemessen", "adecuado", "adéquat", "てきせつ", "адекватный / достаточный"),
    ("B2", "N2", "policy", "Politik / Richtlinie", "política", "politique", "せいさく", "политика / правило"),
    ("B2", "N2", "economy", "Wirtschaft", "economía", "économie", "けいざい", "экономика"),
    ("B2", "N2", "evidence", "Beweis", "evidencia", "preuve", "しょうこ", "доказательство"),
    ("B2", "N2", "impact", "Auswirkung", "impacto", "impact", "えいきょう", "воздействие"),
    ("B2", "N2", "strategy", "Strategie", "estrategia", "stratégie", "せんりゃく", "стратегия"),
    ("B2", "N2", "priority", "Priorität", "prioridad", "priorité", "ゆうせん", "приоритет"),
    ("B2", "N2", "approach", "Ansatz", "enfoque", "approche", "ほうほう", "подход"),
    ("B2", "N2", "method", "Methode", "método", "méthode", "ほうほう", "метод"),
    ("B2", "N2", "process", "Prozess", "proceso", "processus", "かてい", "процесс"),
    ("B2", "N2", "feature", "Merkmal", "característica", "caractéristique", "とくちょう", "характеристика"),
    ("B2", "N2", "resource", "Ressource", "recurso", "ressource", "しげん", "ресурс"),
    ("B2", "N2", "demand", "Nachfrage", "demanda", "demande", "じゅよう", "спрос"),
    ("B2", "N2", "supply", "Angebot", "oferta", "offre", "きょうきゅう", "предложение"),
    ("B2", "N2", "access", "Zugang", "acceso", "accès", "アクセス", "доступ"),

    # ========================================================
    # C1 / N1
    # ========================================================

    ("C1", "N1", "ambiguous", "mehrdeutig", "ambiguo", "ambigu", "あいまい", "неоднозначный"),
    ("C1", "N1", "coherent", "schlüssig", "coherente", "cohérent", "いっかんした", "связный / последовательный"),
    ("C1", "N1", "compelling", "überzeugend", "convincente", "convaincant", "せっとくりょくのある", "убедительный"),
    ("C1", "N1", "contemporary", "zeitgenössisch", "contemporáneo", "contemporain", "げんだいの", "современный"),
    ("C1", "N1", "discrepancy", "Abweichung", "discrepancia", "disparité", "くいちがい", "расхождение"),
    ("C1", "N1", "inevitable", "unvermeidlich", "inevitable", "inévitable", "さけられない", "неизбежный"),
    ("C1", "N1", "intricate", "kompliziert", "intrincado", "complexe", "ふくざつな", "сложный / запутанный"),
    ("C1", "N1", "plausible", "plausibel", "plausible", "plausible", "もっともらしい", "правдоподобный"),
    ("C1", "N1", "underestimate", "unterschätzen", "subestimar", "sous-estimer", "かしょうひょうかする", "недооценивать"),
    ("C1", "N1", "anticipate", "voraussehen", "anticipar", "anticiper", "よそくする", "предвидеть"),
    ("C1", "N1", "facilitate", "erleichtern", "facilitar", "faciliter", "そくしんする", "облегчать / способствовать"),
    ("C1", "N1", "justify", "rechtfertigen", "justificar", "justifier", "せいとうかする", "обосновывать"),
    ("C1", "N1", "refine", "verfeinern", "perfeccionar", "perfectionner", "みがく", "совершенствовать"),
    ("C1", "N1", "undertake", "unternehmen", "emprender", "entreprendre", "とりくむ", "предпринимать / брать на себя"),
    ("C1", "N1", "articulate", "ausdrücken", "articular", "articuler", "ひょうげんする", "чётко выражать"),
    ("C1", "N1", "assert", "behaupten", "afirmar", "affirmer", "しゅちょうする", "утверждать"),
    ("C1", "N1", "constrain", "einschränken", "restringir", "restreindre", "せいやくする", "ограничивать"),
    ("C1", "N1", "contradict", "widersprechen", "contradecir", "contredire", "はんろんする", "противоречить"),
    ("C1", "N1", "devise", "entwickeln", "idear", "concevoir", "かんがえだす", "разрабатывать / придумывать"),
    ("C1", "N1", "diminish", "verringern", "disminuir", "diminuer", "げんしょうする", "уменьшать"),
    ("C1", "N1", "distort", "verzerren", "distorsionar", "fausser", "ゆがめる", "искажать"),
    ("C1", "N1", "elaborate", "ausarbeiten", "elaborar", "élaborer", "くわしくせつめいする", "подробно разрабатывать"),
    ("C1", "N1", "empirical", "empirisch", "empírico", "empirique", "けいけんてき", "эмпирический"),
    ("C1", "N1", "foster", "fördern", "fomentar", "favoriser", "そくしんする", "способствовать / развивать"),
    ("C1", "N1", "inherent", "innewohnend", "inherente", "inhérent", "こゆうの", "неотъемлемый"),
    ("C1", "N1", "innovative", "innovativ", "innovador", "innovant", "かくしんてき", "инновационный"),
    ("C1", "N1", "meticulous", "sorgfältig", "minucioso", "méticuleux", "ちみつな", "тщательный"),
    ("C1", "N1", "notion", "Vorstellung", "noción", "notion", "がいねん", "понятие"),
    ("C1", "N1", "paradigm", "Paradigma", "paradigma", "paradigme", "パラダイム", "парадигма"),
    ("C1", "N1", "profound", "tiefgreifend", "profundo", "profond", "ふかい", "глубокий / значительный"),
    ("C1", "N1", "rational", "vernünftig", "racional", "rationnel", "ごうりてき", "рациональный"),
    ("C1", "N1", "scrutinize", "genau prüfen", "examinar", "examiner", "くわしくしらべる", "тщательно изучать"),
    ("C1", "N1", "subsequent", "nachfolgend", "posterior", "ultérieur", "そのごの", "последующий"),
    ("C1", "N1", "underlying", "zugrunde liegend", "subyacente", "sous-jacent", "はいけいにある", "лежащий в основе"),
    ("C1", "N1", "unprecedented", "beispiellos", "sin precedentes", "sans précédent", "みぞうの", "беспрецедентный"),
    ("C1", "N1", "versatile", "vielseitig", "versátil", "polyvalent", "たような", "многосторонний"),
    ("C1", "N1", "widespread", "weitverbreitet", "generalizado", "répandu", "ひろくひろがった", "широко распространённый"),
    ("C1", "N1", "dilemma", "Dilemma", "dilema", "dilemme", "ジレンマ", "дилемма"),
    ("C1", "N1", "feasible", "durchführbar", "viable", "réalisable", "じっこうかのう", "осуществимый"),
    ("C1", "N1", "inequality", "Ungleichheit", "desigualdad", "inégalité", "ふびょうどう", "неравенство"),
    ("C1", "N1", "legitimate", "legitim", "legítimo", "légitime", "せいとうな", "законный / обоснованный"),
    ("C1", "N1", "marginal", "geringfügig", "marginal", "marginal", "わずかな", "незначительный"),
    ("C1", "N1", "notwithstanding", "ungeachtet", "no obstante", "nonobstant", "にもかかわらず", "несмотря на"),
    ("C1", "N1", "obsolete", "veraltet", "obsoleto", "obsolète", "ふるくてつかわれない", "устаревший"),
    ("C1", "N1", "preliminary", "vorläufig", "preliminar", "préliminaire", "よびてき", "предварительный"),
    ("C1", "N1", "rigorous", "streng", "riguroso", "rigoureux", "げんみつな", "строгий / тщательный"),
    ("C1", "N1", "spontaneous", "spontan", "espontáneo", "spontané", "じはつてき", "спонтанный"),
    ("C1", "N1", "tentative", "vorläufig", "tentativo", "hypothétique", "かりの", "предварительный / неуверенный"),
    ("C1", "N1", "comprehensive", "umfassend", "exhaustivo", "complet", "そうごうてき", "всеобъемлющий"),
    ("C1", "N1", "predominant", "vorherrschend", "predominante", "prédominant", "しゅうせいの", "преобладающий"),
    ("C1", "N1", "resilient", "widerstandsfähig", "resiliente", "résilient", "だんりょくてき", "устойчивый / стойкий"),
    ("C1", "N1", "intrinsic", "wesenseigen", "intrínseco", "intrinsèque", "ほんしつてき", "внутренне присущий"),
    ("C1", "N1", "subtle", "subtil", "sutil", "subtil", "びみょうな", "тонкий / едва заметный"),
    ("C1", "N1", "arbitrary", "willkürlich", "arbitrario", "arbitraire", "にんいてき", "произвольный"),
    ("C1", "N1", "scrutiny", "Prüfung", "escrutinio", "examen minutieux", "くわしいちょうさ", "тщательная проверка"),
    ("C1", "N1", "ambiguity", "Mehrdeutigkeit", "ambigüedad", "ambiguïté", "あいまいさ", "неоднозначность"),
    ("C1", "N1", "coincidence", "Zufall", "coincidencia", "coïncidence", "ぐうぜん", "совпадение"),
    ("C1", "N1", "adaptation", "Anpassung", "adaptación", "adaptation", "てきおう", "адаптация"),
    ("C1", "N1", "persuasion", "Überzeugung", "persuasión", "persuasion", "せっとく", "убеждение"),
    ("C1", "N1", "interpretation", "Interpretation", "interpretación", "interprétation", "かいしゃく", "интерпретация"),
    ("C1", "N1", "implication", "Auswirkung", "implicación", "implication", "がんい", "следствие / подтекст"),
    ("C1", "N1", "distinction", "Unterscheidung", "distinción", "distinction", "くべつ", "различие"),
    ("C1", "N1", "allocation", "Zuteilung", "asignación", "allocation", "はいぶん", "распределение"),
    ("C1", "N1", "constraint", "Einschränkung", "restricción", "contrainte", "せいやく", "ограничение"),
]


# ============================================================
# LANGUAGE CONFIGURATION
# ============================================================

LANGUAGES = {
    "English": {
        "column": 2,
        "flag": "🇬🇧",
        "levels": ["A1", "A2", "B1", "B2", "C1"],
    },
    "German": {
        "column": 3,
        "flag": "🇩🇪",
        "levels": ["A1", "A2", "B1", "B2", "C1"],
    },
    "Spanish": {
        "column": 4,
        "flag": "🇪🇸",
        "levels": ["A1", "A2", "B1", "B2", "C1"],
    },
    "French": {
        "column": 5,
        "flag": "🇫🇷",
        "levels": ["A1", "A2", "B1", "B2", "C1"],
    },
    "Japanese": {
        "column": 6,
        "flag": "🇯🇵",
        "levels": ["N5", "N4", "N3", "N2", "N1"],
    },
    "Russian": {
        "column": 7,
        "flag": "🇷🇺",
        "levels": ["A1", "A2", "B1", "B2", "C1"],
    },
}

CEFR_ORDER = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
}

JLPT_ORDER = {
    "N5": 1,
    "N4": 2,
    "N3": 3,
    "N2": 4,
    "N1": 5,
}


# ============================================================
# GENERATED DECKS
# ============================================================

def build_deck(
    language: str,
    level: str,
) -> List[
    Tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
    ]
]:

    """
    Returns:

        (
            front,
            english,
            german,
            spanish,
            french,
            japanese,
            russian,
        )
    """

    if language not in LANGUAGES:

        raise ValueError(
            f"Unknown language: {language}"
        )

    if level not in LANGUAGES[language]["levels"]:

        raise ValueError(
            f"Unknown level {level} for {language}"
        )

    config = LANGUAGES[language]

    column = config["column"]

    cards = []

    for entry in VOCABULARY:

        cefr_level = entry[0]
        jlpt_level = entry[1]

        if language == "Japanese":

            if (
                JLPT_ORDER[jlpt_level]
                > JLPT_ORDER[level]
            ):
                continue

        else:

            if (
                CEFR_ORDER[cefr_level]
                > CEFR_ORDER[level]
            ):
                continue

        front = entry[column]

        english = entry[2]
        german = entry[3]
        spanish = entry[4]
        french = entry[5]
        japanese = entry[6]
        russian = entry[7]

        cards.append(
            (
                front,
                english,
                german,
                spanish,
                french,
                japanese,
                russian,
            )
        )

    return cards


def get_all_decks():

    decks = []

    for language, config in LANGUAGES.items():

        for level in config["levels"]:

            decks.append(
                f"{language} {level}"
            )

    return decks


def parse_deck_name(
    name: str,
):

    value = name.strip().lower()

    for language, config in LANGUAGES.items():

        for level in config["levels"]:

            expected = (
                f"{language} {level}"
                .lower()
            )

            if value == expected:

                return (
                    language,
                    level,
                )

    return None


# ============================================================
# DATABASE
# ============================================================

def get_db():

    db = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    return db


def utc_now():

    return datetime.now(
        timezone.utc
    )


def utc_iso():

    return utc_now().isoformat()


def parse_dt(
    value,
):

    dt = datetime.fromisoformat(
        value
    )

    if dt.tzinfo is None:

        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt


def init_database():

    with get_db() as db:

        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                name TEXT NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE(
                    user_id,
                    name COLLATE NOCASE
                )
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                deck_id INTEGER NOT NULL,

                front TEXT NOT NULL,

                back TEXT NOT NULL,

                english TEXT NOT NULL,

                german TEXT,

                spanish TEXT,

                french TEXT,

                japanese TEXT,

                russian TEXT NOT NULL,

                due_at TEXT NOT NULL,

                interval_days REAL NOT NULL DEFAULT 0,

                ease_factor REAL NOT NULL DEFAULT 2.50,

                repetitions INTEGER NOT NULL DEFAULT 0,

                lapses INTEGER NOT NULL DEFAULT 0,

                total_reviews INTEGER NOT NULL DEFAULT 0,

                correct_reviews INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                FOREIGN KEY(deck_id)
                    REFERENCES decks(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                card_id INTEGER NOT NULL,

                user_id INTEGER NOT NULL,

                rating INTEGER NOT NULL,

                old_interval REAL NOT NULL,

                new_interval REAL NOT NULL,

                reviewed_at TEXT NOT NULL,

                FOREIGN KEY(card_id)
                    REFERENCES cards(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_cards_due
            ON cards(deck_id, due_at);

            CREATE INDEX IF NOT EXISTS idx_reviews_user
            ON reviews(user_id);
            """
        )

        db.commit()

    logger.info(
        "Database initialized."
    )


def migrate_database():

    with get_db() as db:

        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(cards)"
            ).fetchall()
        }

        logger.info(
            "Existing card columns: %s",
            sorted(columns),
        )

        required_columns = {
            "english": "TEXT",
            "german": "TEXT",
            "spanish": "TEXT",
            "french": "TEXT",
            "japanese": "TEXT",
            "russian": "TEXT",
        }

        for column, column_type in required_columns.items():

            if column not in columns:

                logger.info(
                    "Adding missing column: %s",
                    column,
                )

                db.execute(
                    f"""
                    ALTER TABLE cards
                    ADD COLUMN {column} {column_type}
                    """
                )

        db.commit()

    logger.info(
        "Database migration completed successfully."
    )


# ============================================================
# AUTO DECK DATABASE
# ============================================================

async def ensure_auto_deck(
    user_id: int,
    deck_name: str,
):

    parsed = parse_deck_name(
        deck_name
    )

    if not parsed:

        raise ValueError(
            f"Automatic deck not found: {deck_name}"
        )

    language, level = parsed

    cards = build_deck(
        language,
        level,
    )

    if not cards:

        raise ValueError(
            f"No cards found for {deck_name}"
        )

    async with db_lock:

        def operation():

            with get_db() as db:

                deck = db.execute(
                    """
                    SELECT *
                    FROM decks
                    WHERE user_id = ?
                      AND name = ?
                    COLLATE NOCASE
                    """,
                    (
                        user_id,
                        deck_name,
                    ),
                ).fetchone()

                if not deck:

                    count = db.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM decks
                        WHERE user_id = ?
                        """,
                        (
                            user_id,
                        ),
                    ).fetchone()["count"]

                    if count >= MAX_DECKS_PER_USER:

                        raise ValueError(
                            "Deck limit reached."
                        )

                    cursor = db.execute(
                        """
                        INSERT INTO decks (
                            user_id,
                            name,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            user_id,
                            deck_name,
                            utc_iso(),
                        ),
                    )

                    deck_id = cursor.lastrowid

                    logger.info(
                        "Created automatic deck %s with id %s",
                        deck_name,
                        deck_id,
                    )

                else:

                    deck_id = deck["id"]

                existing = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM cards
                    WHERE deck_id = ?
                    """,
                    (
                        deck_id,
                    ),
                ).fetchone()["count"]

                if existing > MAX_CARDS_PER_DECK:

                    raise ValueError(
                        "Card limit exceeded."
                    )

                added = 0
                updated = 0

                for (
                    front,
                    english,
                    german,
                    spanish,
                    french,
                    japanese,
                    russian,
                ) in cards:

                    found = db.execute(
                        """
                        SELECT id
                        FROM cards
                        WHERE deck_id = ?
                          AND front = ?
                        LIMIT 1
                        """,
                        (
                            deck_id,
                            front,
                        ),
                    ).fetchone()

                    if found:

                        db.execute(
                            """
                            UPDATE cards
                            SET
                                back = ?,
                                english = ?,
                                german = ?,
                                spanish = ?,
                                french = ?,
                                japanese = ?,
                                russian = ?
                            WHERE id = ?
                            """,
                            (
                                english,
                                english,
                                german,
                                spanish,
                                french,
                                japanese,
                                russian,
                                found["id"],
                            ),
                        )

                        updated += 1

                    else:

                        if (
                            existing + added
                            >= MAX_CARDS_PER_DECK
                        ):

                            raise ValueError(
                                "Card limit reached."
                            )

                        db.execute(
                            """
                            INSERT INTO cards (
                                deck_id,
                                front,
                                back,
                                english,
                                german,
                                spanish,
                                french,
                                japanese,
                                russian,
                                due_at,
                                created_at
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?
                            )
                            """,
                            (
                                deck_id,
                                front,
                                english,
                                english,
                                german,
                                spanish,
                                french,
                                japanese,
                                russian,
                                utc_iso(),
                                utc_iso(),
                            ),
                        )

                        added += 1

                db.commit()

                return (
                    len(cards),
                    added,
                    updated,
                    deck_id,
                )

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# DECK QUERIES
# ============================================================

async def get_deck(
    user_id,
    name,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                return db.execute(
                    """
                    SELECT *
                    FROM decks
                    WHERE user_id = ?
                      AND name = ?
                    COLLATE NOCASE
                    """,
                    (
                        user_id,
                        name,
                    ),
                ).fetchone()

        return await asyncio.to_thread(
            operation
        )


async def list_user_decks(
    user_id,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                return db.execute(
                    """
                    SELECT
                        d.name,
                        COUNT(c.id) AS cards,
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN c.due_at <= ?
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS due
                    FROM decks d
                    LEFT JOIN cards c
                        ON c.deck_id = d.id
                    WHERE d.user_id = ?
                    GROUP BY d.id
                    ORDER BY d.name
                    """,
                    (
                        utc_iso(),
                        user_id,
                    ),
                ).fetchall()

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# CARD QUERIES
# ============================================================

async def get_due_card(
    user_id,
    deck_name,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                return db.execute(
                    """
                    SELECT
                        c.*,
                        d.name AS deck_name
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE d.user_id = ?
                      AND d.name = ?
                      AND c.due_at <= ?
                    COLLATE NOCASE
                    ORDER BY
                        c.due_at ASC,
                        c.repetitions ASC,
                        c.id ASC
                    LIMIT 1
                    """,
                    (
                        user_id,
                        deck_name,
                        utc_iso(),
                    ),
                ).fetchone()

        return await asyncio.to_thread(
            operation
        )


async def get_any_card(
    user_id,
    deck_name,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                return db.execute(
                    """
                    SELECT
                        c.*,
                        d.name AS deck_name
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE d.user_id = ?
                      AND d.name = ?
                    COLLATE NOCASE
                    ORDER BY
                        c.due_at ASC,
                        c.id ASC
                    LIMIT 1
                    """,
                    (
                        user_id,
                        deck_name,
                    ),
                ).fetchone()

        return await asyncio.to_thread(
            operation
        )


async def get_card(
    user_id,
    card_id,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                return db.execute(
                    """
                    SELECT
                        c.*,
                        d.name AS deck_name,
                        d.user_id
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE c.id = ?
                      AND d.user_id = ?
                    """,
                    (
                        card_id,
                        user_id,
                    ),
                ).fetchone()

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# SPACED REPETITION
# ============================================================

def calculate_next_review(
    quality,
    repetitions,
    interval_days,
    ease_factor,
):

    if not 0 <= quality <= 5:

        raise ValueError(
            "Quality must be between 0 and 5."
        )

    lapses_delta = 0
    correct_delta = 0

    if quality < 3:

        repetitions = 0

        lapses_delta = 1

        interval_days = 0.007

        ease_factor = max(
            1.30,
            ease_factor - 0.20,
        )

        return (
            repetitions,
            interval_days,
            ease_factor,
            lapses_delta,
            correct_delta,
        )

    correct_delta = 1

    if repetitions == 0:

        interval_days = 1

    elif repetitions == 1:

        interval_days = 6

    else:

        interval_days = (
            interval_days
            * ease_factor
        )

    if quality == 3:

        ease_factor -= 0.15

    elif quality == 5:

        ease_factor += 0.15

        interval_days *= 1.30

    ease_factor = max(
        1.30,
        min(
            3.00,
            ease_factor,
        ),
    )

    repetitions += 1

    interval_days = max(
        1,
        min(
            interval_days,
            3650,
        ),
    )

    return (
        repetitions,
        interval_days,
        ease_factor,
        lapses_delta,
        correct_delta,
    )


def format_interval(
    days,
):

    if days < 1:

        minutes = max(
            1,
            round(
                days * 24 * 60
            ),
        )

        return f"{minutes} min."

    if days < 2:

        return "1 day"

    if days < 30:

        return f"{round(days)} days"

    if days < 365:

        return (
            f"{round(days / 30)} months"
        )

    return (
        f"{round(days / 365, 1)} years"
    )


def rating_name(
    quality,
):

    return {
        0: "Again",
        3: "Hard",
        4: "Good",
        5: "Easy",
    }.get(
        quality,
        "Again",
    )


# ============================================================
# REVIEW
# ============================================================

async def review_card(
    user_id,
    card_id,
    quality,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                card = db.execute(
                    """
                    SELECT
                        c.*,
                        d.name AS deck_name
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE c.id = ?
                      AND d.user_id = ?
                    """,
                    (
                        card_id,
                        user_id,
                    ),
                ).fetchone()

                if not card:

                    raise ValueError(
                        "Card not found."
                    )

                (
                    repetitions,
                    interval_days,
                    ease_factor,
                    lapses_delta,
                    correct_delta,
                ) = calculate_next_review(
                    quality,
                    card["repetitions"],
                    card["interval_days"],
                    card["ease_factor"],
                )

                now = utc_now()

                due_at = (
                    now
                    + timedelta(
                        days=interval_days
                    )
                ).isoformat()

                db.execute(
                    """
                    UPDATE cards
                    SET
                        due_at = ?,
                        interval_days = ?,
                        ease_factor = ?,
                        repetitions = ?,
                        lapses =
                            lapses + ?,
                        total_reviews =
                            total_reviews + 1,
                        correct_reviews =
                            correct_reviews + ?
                    WHERE id = ?
                    """,
                    (
                        due_at,
                        interval_days,
                        ease_factor,
                        repetitions,
                        lapses_delta,
                        correct_delta,
                        card_id,
                    ),
                )

                db.execute(
                    """
                    INSERT INTO reviews (
                        card_id,
                        user_id,
                        rating,
                        old_interval,
                        new_interval,
                        reviewed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card_id,
                        user_id,
                        quality,
                        card["interval_days"],
                        interval_days,
                        now.isoformat(),
                    ),
                )

                db.commit()

                return {
                    "deck_name": card["deck_name"],
                    "interval_days": interval_days,
                    "ease_factor": ease_factor,
                    "repetitions": repetitions,
                }

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# STATISTICS
# ============================================================

async def get_stats(
    user_id,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                decks = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM decks
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()["count"]

                cards = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE d.user_id = ?
                    """,
                    (user_id,),
                ).fetchone()["count"]

                due = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM cards c
                    JOIN decks d
                        ON d.id = c.deck_id
                    WHERE d.user_id = ?
                      AND c.due_at <= ?
                    """,
                    (
                        user_id,
                        utc_iso(),
                    ),
                ).fetchone()["count"]

                reviews = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM reviews
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()["count"]

                correct = db.execute(
                    """
                    SELECT
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN rating >= 3
                                    THEN 1
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS count
                    FROM reviews
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()["count"]

                return {
                    "decks": decks,
                    "cards": cards,
                    "due": due,
                    "reviews": reviews,
                    "correct": correct,
                }

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# STUDY SESSIONS
# ============================================================

def cleanup_sessions():

    now = utc_now()

    expired = []

    for session_id, session in list(
        study_sessions.items()
    ):

        created_at = session.get(
            "created_at"
        )

        if not created_at:

            expired.append(
                session_id
            )

            continue

        age = (
            now - created_at
        ).total_seconds()

        if (
            age
            > SESSION_TIMEOUT_MINUTES * 60
        ):

            expired.append(
                session_id
            )

    for session_id in expired:

        study_sessions.pop(
            session_id,
            None,
        )


async def session_cleanup_loop():

    while not shutdown_event.is_set():

        try:

            await asyncio.sleep(
                300
            )

            cleanup_sessions()

        except asyncio.CancelledError:

            break

        except Exception:

            logger.exception(
                "Session cleanup failed."
            )


async def create_study_session(
    user_id,
    deck_name,
):

    deck = await get_deck(
        user_id,
        deck_name,
    )

    if not deck:

        return (
            False,
            "Deck not found.",
        )

    card = await get_due_card(
        user_id,
        deck_name,
    )

    if not card:

        any_card = await get_any_card(
            user_id,
            deck_name,
        )

        if not any_card:

            return (
                False,
                "This deck has no cards.",
            )

        due_at = parse_dt(
            any_card["due_at"]
        )

        delta = (
            due_at - utc_now()
        )

        if delta.total_seconds() <= 0:

            return (
                False,
                "All cards are completed!",
            )

        minutes = max(
            1,
            round(
                delta.total_seconds()
                / 60
            ),
        )

        if minutes < 60:

            text = (
                "🎉 No cards are due right now.\n\n"
                f"Next card in about "
                f"{minutes} minutes."
            )

        else:

            hours = max(
                1,
                round(
                    minutes / 60
                ),
            )

            text = (
                "🎉 No cards are due right now.\n\n"
                f"Next card in about "
                f"{hours} hours."
            )

        return (
            False,
            text,
        )

    session_id = str(
        uuid.uuid4()
    )

    study_sessions[
        session_id
    ] = {
        "user_id": user_id,
        "card_id": card["id"],
        "deck_name": deck_name,
        "revealed": False,
        "created_at": utc_now(),
    }

    return (
        True,
        session_id,
    )


# ============================================================
# KEYBOARDS
# ============================================================

def language_flag(
    deck_name,
):

    for language, config in LANGUAGES.items():

        if deck_name.startswith(
            language
        ):

            return config["flag"]

    return "📚"


def auto_decks_keyboard():

    builder = (
        InlineKeyboardBuilder()
    )

    for deck_name in get_all_decks():

        builder.button(
            text=(
                language_flag(
                    deck_name
                )
                + " "
                + deck_name
            ),
            callback_data=(
                "auto:"
                + deck_name
            ),
        )

    builder.adjust(1)

    return builder.as_markup()


def reveal_keyboard(
    session_id,
):

    builder = (
        InlineKeyboardBuilder()
    )

    builder.button(
        text="👁 Show answer",
        callback_data=(
            f"reveal:{session_id}"
        ),
    )

    return builder.as_markup()


def rating_keyboard(
    session_id,
):

    builder = (
        InlineKeyboardBuilder()
    )

    builder.button(
        text="🔴 Again",
        callback_data=(
            f"rate:{session_id}:0"
        ),
    )

    builder.button(
        text="🟠 Hard",
        callback_data=(
            f"rate:{session_id}:3"
        ),
    )

    builder.button(
        text="🟢 Good",
        callback_data=(
            f"rate:{session_id}:4"
        ),
    )

    builder.button(
        text="🔵 Easy",
        callback_data=(
            f"rate:{session_id}:5"
        ),
    )

    builder.adjust(2)

    return builder.as_markup()


# ============================================================
# ANSWER FORMAT
# ============================================================

def build_answer(
    card,
):

    deck_name = card["deck_name"]

    if deck_name.startswith(
        "English"
    ):

        return (
            "🇩🇪 <b>German:</b>\n"
            f"{html.escape(card['german'] or '')}\n\n"

            "🇪🇸 <b>Spanish:</b>\n"
            f"{html.escape(card['spanish'] or '')}\n\n"

            "🇫🇷 <b>French:</b>\n"
            f"{html.escape(card['french'] or '')}\n\n"

            "🇯🇵 <b>Japanese:</b>\n"
            f"{html.escape(card['japanese'] or '')}\n\n"

            "🇷🇺 <b>Russian:</b>\n"
            f"{html.escape(card['russian'] or '')}"
        )

    if deck_name.startswith(
        "Russian"
    ):

        return (
            "🇬🇧 <b>English:</b>\n"
            f"{html.escape(card['english'] or '')}\n\n"

            "🇩🇪 <b>German:</b>\n"
            f"{html.escape(card['german'] or '')}\n\n"

            "🇪🇸 <b>Spanish:</b>\n"
            f"{html.escape(card['spanish'] or '')}\n\n"

            "🇫🇷 <b>French:</b>\n"
            f"{html.escape(card['french'] or '')}\n\n"

            "🇯🇵 <b>Japanese:</b>\n"
            f"{html.escape(card['japanese'] or '')}"
        )

    if deck_name.startswith(
        "German"
    ):

        return (
            "🇬🇧 <b>English:</b>\n"
            f"{html.escape(card['english'] or '')}\n\n"

            "🇷🇺 <b>Russian:</b>\n"
            f"{html.escape(card['russian'] or '')}"
        )

    if deck_name.startswith(
        "Spanish"
    ):

        return (
            "🇬🇧 <b>English:</b>\n"
            f"{html.escape(card['english'] or '')}\n\n"

            "🇷🇺 <b>Russian:</b>\n"
            f"{html.escape(card['russian'] or '')}"
        )

    if deck_name.startswith(
        "French"
    ):

        return (
            "🇬🇧 <b>English:</b>\n"
            f"{html.escape(card['english'] or '')}\n\n"

            "🇷🇺 <b>Russian:</b>\n"
            f"{html.escape(card['russian'] or '')}"
        )

    if deck_name.startswith(
        "Japanese"
    ):

        return (
            "🇬🇧 <b>English:</b>\n"
            f"{html.escape(card['english'] or '')}\n\n"

            "🇷🇺 <b>Russian:</b>\n"
            f"{html.escape(card['russian'] or '')}"
        )

    return (
        "🇬🇧 <b>English:</b>\n"
        f"{html.escape(card['english'] or '')}\n\n"

        "🇷🇺 <b>Russian:</b>\n"
        f"{html.escape(card['russian'] or '')}"
    )


# ============================================================
# SHOW CARD
# ============================================================

async def show_card(
    message,
    session_id,
):

    session = study_sessions.get(
        session_id
    )

    if not session:

        logger.error(
            "Study session not found: %s",
            session_id,
        )

        return False

    card = await get_card(
        session["user_id"],
        session["card_id"],
    )

    if not card:

        logger.error(
            "Card not found for session: %s",
            session_id,
        )

        return False

    await message.answer(
        "🧠 <b>Flashcard</b>\n\n"
        f"📚 <b>{html.escape(card['deck_name'])}</b>\n\n"
        f"❓ <b>{html.escape(card['front'])}</b>\n\n"
        "Think about the meaning before revealing the answer.",
        reply_markup=reveal_keyboard(
            session_id
        ),
        parse_mode="HTML",
    )

    return True


# ============================================================
# /START
# ============================================================

@dp.message(
    CommandStart()
)
async def start_handler(
    message: Message,
):

    await message.answer(
        "🧠 <b>Flashcards Bot</b>\n\n"

        "Learn vocabulary with "
        "spaced repetition.\n\n"

        "<b>Languages:</b>\n"
        "🇬🇧 English A1–C1\n"
        "🇩🇪 German A1–C1\n"
        "🇪🇸 Spanish A1–C1\n"
        "🇫🇷 French A1–C1\n"
        "🇯🇵 Japanese N5–N1\n"
        "🇷🇺 Russian A1–C1\n\n"

        "<b>Translation mode:</b>\n"
        "🇬🇧 English → German + Spanish + French + Japanese + Russian\n"
        "🇷🇺 Russian → English + German + Spanish + French + Japanese\n"
        "Other languages → English + Russian\n\n"

        "<b>Quick start:</b>\n"
        "<code>/learn English A1</code>\n"
        "<code>/learn Russian A1</code>\n\n"

        "Use <code>/help</code> for all commands.",
        parse_mode="HTML",
    )


# ============================================================
# /HELP
# ============================================================

@dp.message(
    Command("help")
)
async def help_handler(
    message: Message,
):

    await message.answer(
        "<b>📚 Commands</b>\n\n"

        "<b>Automatic learning:</b>\n"
        "<code>/learn</code>\n"
        "<code>/learn English A2</code>\n"
        "<code>/learn German B1</code>\n"
        "<code>/learn Spanish B2</code>\n"
        "<code>/learn French C1</code>\n"
        "<code>/learn Japanese N3</code>\n"
        "<code>/learn Russian A1</code>\n\n"

        "<b>Custom decks:</b>\n"
        "<code>/deck My Words</code>\n"
        "<code>/add My Words | hello | привет</code>\n"
        "<code>/study My Words</code>\n\n"

        "<b>Other:</b>\n"
        "<code>/decks</code>\n"
        "<code>/stats</code>",
        parse_mode="HTML",
    )


# ============================================================
# /LEARN
# ============================================================

@dp.message(
    Command("learn")
)
async def learn_handler(
    message: Message,
):

    args = (
        message.text.partition(
            " "
        )[2].strip()
        if message.text
        else ""
    )

    if not args:

        await message.answer(
            "📚 <b>Choose a language and level:</b>",
            reply_markup=auto_decks_keyboard(),
            parse_mode="HTML",
        )

        return

    parsed = parse_deck_name(
        args
    )

    if not parsed:

        await message.answer(
            "❌ Automatic deck not found.\n\n"
            "Use /learn to see all available decks."
        )

        return

    language, level = parsed

    deck_name = (
        f"{language} {level}"
    )

    try:

        (
            total,
            added,
            updated,
            _,
        ) = await ensure_auto_deck(
            message.from_user.id,
            deck_name,
        )

        await message.answer(
            "✅ <b>Deck ready!</b>\n\n"
            f"📚 {html.escape(deck_name)}\n"
            f"🃏 Available cards: {total}\n"
            f"➕ New cards added: {added}\n"
            f"🔄 Updated translations: {updated}\n\n"
            "🚀 Starting study...",
            parse_mode="HTML",
        )

        success, result = (
            await create_study_session(
                message.from_user.id,
                deck_name,
            )
        )

        if not success:

            await message.answer(
                result
            )

            return

        shown = await show_card(
            message,
            result,
        )

        if not shown:

            await message.answer(
                "❌ Could not display the first card."
            )

    except Exception as exc:

        logger.exception(
            "Failed to start automatic deck %s: %s",
            deck_name,
            exc,
        )

        await message.answer(
            "❌ Could not load the deck.\n\n"
            f"Error: <code>{html.escape(type(exc).__name__)}</code>\n"
            "Check the bot console for the full traceback.",
            parse_mode="HTML",
        )


# ============================================================
# AUTO DECK CALLBACK
# ============================================================

@dp.callback_query(
    F.data.startswith("auto:")
)
async def auto_deck_callback(
    callback: CallbackQuery,
):

    deck_name = (
        callback.data[5:].strip()
    )

    logger.info(
        "User %s selected automatic deck: %s",
        callback.from_user.id,
        deck_name,
    )

    try:

        parsed = parse_deck_name(
            deck_name
        )

        if not parsed:

            logger.error(
                "Deck parser could not find: %r",
                deck_name,
            )

            await callback.answer(
                "Deck not found.",
                show_alert=True,
            )

            return

        (
            total,
            added,
            updated,
            deck_id,
        ) = await ensure_auto_deck(
            callback.from_user.id,
            deck_name,
        )

        logger.info(
            "Automatic deck ready: name=%s id=%s total=%s added=%s updated=%s",
            deck_name,
            deck_id,
            total,
            added,
            updated,
        )

        await callback.answer(
            "Ready!"
        )

        success, result = (
            await create_study_session(
                callback.from_user.id,
                deck_name,
            )
        )

        if not success:

            logger.warning(
                "Could not create study session for %s: %s",
                deck_name,
                result,
            )

            if callback.message:

                await callback.message.answer(
                    str(result)
                )

            return

        if not callback.message:

            return

        await callback.message.answer(
            "🚀 <b>Starting study!</b>\n\n"
            f"📚 {html.escape(deck_name)}\n"
            f"🃏 Cards: {total}\n"
            f"➕ Added: {added}\n"
            f"🔄 Updated: {updated}",
            parse_mode="HTML",
        )

        shown = await show_card(
            callback.message,
            result,
        )

        if not shown:

            logger.error(
                "show_card() returned False for session %s",
                result,
            )

            await callback.message.answer(
                "❌ Could not display the first card."
            )

    except ValueError as exc:

        logger.exception(
            "ValueError while loading automatic deck: %s",
            exc,
        )

        await callback.answer(
            f"Error: {str(exc)}",
            show_alert=True,
        )

    except sqlite3.Error as exc:

        logger.exception(
            "SQLite error while loading automatic deck: %s",
            exc,
        )

        await callback.answer(
            "Database error. Check the bot console.",
            show_alert=True,
        )

    except Exception as exc:

        logger.exception(
            "Automatic deck callback failed: %s",
            exc,
        )

        await callback.answer(
            f"Error: {type(exc).__name__}",
            show_alert=True,
        )


# ============================================================
# /DECK
# ============================================================

@dp.message(
    Command("deck")
)
async def deck_handler(
    message: Message,
):

    name = (
        message.text.partition(
            " "
        )[2].strip()
        if message.text
        else ""
    )

    if not name:

        await message.answer(
            "Usage:\n"
            "<code>/deck My Words</code>",
            parse_mode="HTML",
        )

        return

    if len(name) > 100:

        await message.answer(
            "❌ Deck name is too long."
        )

        return

    try:

        await create_custom_deck(
            message.from_user.id,
            name,
        )

        await message.answer(
            "✅ Deck created!\n\n"
            f"📚 <b>{html.escape(name)}</b>",
            parse_mode="HTML",
        )

    except ValueError as exc:

        await message.answer(
            f"❌ {html.escape(str(exc))}"
        )

    except Exception as exc:

        logger.exception(
            "Failed to create custom deck: %s",
            exc,
        )

        await message.answer(
            "❌ Could not create the deck."
        )


async def create_custom_deck(
    user_id,
    name,
):

    async with db_lock:

        def operation():

            with get_db() as db:

                count = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM decks
                    WHERE user_id = ?
                    """,
                    (
                        user_id,
                    ),
                ).fetchone()["count"]

                if (
                    count
                    >= MAX_DECKS_PER_USER
                ):

                    raise ValueError(
                        "Deck limit reached."
                    )

                try:

                    cursor = db.execute(
                        """
                        INSERT INTO decks (
                            user_id,
                            name,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            user_id,
                            name,
                            utc_iso(),
                        ),
                    )

                    db.commit()

                    return cursor.lastrowid

                except sqlite3.IntegrityError:

                    raise ValueError(
                        "This deck already exists."
                    )

        return await asyncio.to_thread(
            operation
        )


# ============================================================
# /ADD
# ============================================================

@dp.message(
    Command("add")
)
async def add_handler(
    message: Message,
):

    raw = (
        message.text.partition(
            " "
        )[2].strip()
        if message.text
        else ""
    )

    parts = [
        part.strip()
        for part in raw.split("|")
    ]

    if len(parts) != 3:

        await message.answer(
            "Usage:\n"
            "<code>/add Deck | front | back</code>\n\n"
            "Example:\n"
            "<code>/add My Words | "
            "hello | привет</code>",
            parse_mode="HTML",
        )

        return

    deck_name, front, back = parts

    deck = await get_deck(
        message.from_user.id,
        deck_name,
    )

    if not deck:

        await message.answer(
            "❌ Deck not found."
        )

        return

    async with db_lock:

        def operation():

            with get_db() as db:

                count = db.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM cards
                    WHERE deck_id = ?
                    """,
                    (
                        deck["id"],
                    ),
                ).fetchone()["count"]

                if (
                    count
                    >= MAX_CARDS_PER_DECK
                ):

                    raise ValueError(
                        "Card limit reached."
                    )

                cursor = db.execute(
                    """
                    INSERT INTO cards (
                        deck_id,
                        front,
                        back,
                        english,
                        german,
                        spanish,
                        french,
                        japanese,
                        russian,
                        due_at,
                        created_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        deck["id"],
                        front,
                        back,
                        front,
                        None,
                        None,
                        None,
                        None,
                        back,
                        utc_iso(),
                        utc_iso(),
                    ),
                )

                db.commit()

                return cursor.lastrowid

        try:

            await asyncio.to_thread(
                operation
            )

        except ValueError as exc:

            await message.answer(
                f"❌ {html.escape(str(exc))}"
            )

            return

        except sqlite3.IntegrityError as exc:

            logger.exception(
                "Failed to add card: %s",
                exc,
            )

            await message.answer(
                "❌ Could not add the card."
            )

            return

    await message.answer(
        "✅ Card added!\n\n"
        f"❓ {html.escape(front)}\n"
        f"💡 {html.escape(back)}",
        parse_mode="HTML",
    )


# ============================================================
# /DECKS
# ============================================================

@dp.message(
    Command("decks")
)
async def decks_handler(
    message: Message,
):

    decks = await list_user_decks(
        message.from_user.id
    )

    if not decks:

        await message.answer(
            "📭 No decks yet.\n\n"
            "Try:\n"
            "<code>/learn English A1</code>",
            parse_mode="HTML",
        )

        return

    lines = [
        "📚 <b>Your decks</b>\n"
    ]

    for deck in decks:

        lines.append(
            f"📖 <b>{html.escape(deck['name'])}</b>\n"
            f"🃏 Cards: {deck['cards']}\n"
            f"⏰ Due: {deck['due']}\n"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# /STUDY
# ============================================================

@dp.message(
    Command("study")
)
async def study_handler(
    message: Message,
):

    deck_name = (
        message.text.partition(
            " "
        )[2].strip()
        if message.text
        else ""
    )

    if not deck_name:

        await message.answer(
            "Usage:\n"
            "<code>/study English B1</code>\n"
            "<code>/study Russian A1</code>",
            parse_mode="HTML",
        )

        return

    # Automatically create built-in deck.
    if parse_deck_name(
        deck_name
    ):

        try:

            await ensure_auto_deck(
                message.from_user.id,
                deck_name,
            )

        except Exception as exc:

            logger.exception(
                "Failed to ensure automatic deck: %s",
                exc,
            )

            await message.answer(
                "❌ Could not prepare the automatic deck."
            )

            return

    success, result = (
        await create_study_session(
            message.from_user.id,
            deck_name,
        )
    )

    if not success:

        await message.answer(
            result
        )

        return

    shown = await show_card(
        message,
        result,
    )

    if not shown:

        await message.answer(
            "❌ Could not display the card."
        )


# ============================================================
# /STATS
# ============================================================

@dp.message(
    Command("stats")
)
async def stats_handler(
    message: Message,
):

    stats = await get_stats(
        message.from_user.id
    )

    accuracy = 0

    if stats["reviews"]:

        accuracy = (
            stats["correct"]
            / stats["reviews"]
            * 100
        )

    await message.answer(
        "📊 <b>Statistics</b>\n\n"
        f"📚 Decks: {stats['decks']}\n"
        f"🃏 Cards: {stats['cards']}\n"
        f"⏰ Due: {stats['due']}\n"
        f"🔄 Reviews: {stats['reviews']}\n"
        f"🎯 Correct: {stats['correct']}\n"
        f"📈 Accuracy: {accuracy:.1f}%",
        parse_mode="HTML",
    )


# ============================================================
# REVEAL
# ============================================================

@dp.callback_query(
    F.data.startswith("reveal:")
)
async def reveal_handler(
    callback: CallbackQuery,
):

    session_id = callback.data[
        7:
    ]

    session = study_sessions.get(
        session_id
    )

    if not session:

        await callback.answer(
            "Study session expired.",
            show_alert=True,
        )

        return

    if (
        session["user_id"]
        != callback.from_user.id
    ):

        await callback.answer(
            "This is not your card.",
            show_alert=True,
        )

        return

    card = await get_card(
        callback.from_user.id,
        session["card_id"],
    )

    if not card:

        await callback.answer(
            "Card not found.",
            show_alert=True,
        )

        return

    session["revealed"] = True

    answer = build_answer(
        card
    )

    if callback.message:

        await callback.message.edit_text(
            "🧠 <b>Flashcard</b>\n\n"
            f"📚 <b>{html.escape(card['deck_name'])}</b>\n\n"
            f"❓ <b>{html.escape(card['front'])}</b>\n\n"
            f"💡 <b>Answer</b>\n\n"
            f"{answer}\n\n"
            "How well did you remember it?",
            reply_markup=rating_keyboard(
                session_id
            ),
            parse_mode="HTML",
        )

    await callback.answer()


# ============================================================
# RATE
# ============================================================

@dp.callback_query(
    F.data.startswith("rate:")
)
async def rate_handler(
    callback: CallbackQuery,
):

    parts = callback.data.split(
        ":"
    )

    if len(parts) != 3:

        await callback.answer(
            "Invalid rating.",
            show_alert=True,
        )

        return

    session_id = parts[1]

    try:

        quality = int(
            parts[2]
        )

    except ValueError:

        await callback.answer(
            "Invalid rating.",
            show_alert=True,
        )

        return

    session = study_sessions.get(
        session_id
    )

    if not session:

        await callback.answer(
            "Study session expired.",
            show_alert=True,
        )

        return

    if (
        session["user_id"]
        != callback.from_user.id
    ):

        await callback.answer(
            "This is not your card.",
            show_alert=True,
        )

        return

    if not session["revealed"]:

        await callback.answer(
            "Reveal the answer first.",
            show_alert=True,
        )

        return

    try:

        result = await review_card(
            callback.from_user.id,
            session["card_id"],
            quality,
        )

    except Exception as exc:

        logger.exception(
            "Review failed: %s",
            exc,
        )

        await callback.answer(
            "Could not save the rating.",
            show_alert=True,
        )

        return

    study_sessions.pop(
        session_id,
        None,
    )

    await callback.answer(
        rating_name(quality)
    )

    success, next_result = (
        await create_study_session(
            callback.from_user.id,
            result["deck_name"],
        )
    )

    if not success:

        if callback.message:

            await callback.message.edit_text(
                "✅ <b>Rating saved!</b>\n\n"
                f"🎯 {rating_name(quality)}\n"
                f"📅 Next review: "
                f"<b>{format_interval(result['interval_days'])}</b>\n\n"
                f"{next_result}",
                parse_mode="HTML",
            )

        return

    if callback.message:

        try:

            await callback.message.edit_text(
                "✅ <b>Rating saved!</b>\n\n"
                f"🎯 {rating_name(quality)}\n"
                f"📅 Next review: "
                f"<b>{format_interval(result['interval_days'])}</b>\n\n"
                "➡️ Next card...",
                parse_mode="HTML",
            )

        except Exception:

            pass

        await asyncio.sleep(
            0.6
        )

        await show_card(
            callback.message,
            next_result,
        )


# ============================================================
# FALLBACK
# ============================================================

@dp.message(
    F.text
)
async def text_handler(
    message: Message,
):

    if (
        message.text
        and message.text.startswith("/")
    ):

        return

    await message.answer(
        "Use <code>/help</code> to see available commands.",
        parse_mode="HTML",
    )


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def error_handler(
    event,
):

    logger.exception(
        "Unhandled Telegram error: %s",
        event.exception,
    )


# ============================================================
# TESTS
# ============================================================

class FlashcardsTests(
    unittest.TestCase
):

    def test_vocabulary_not_empty(
        self,
    ):

        self.assertGreater(
            len(VOCABULARY),
            100,
        )

    def test_vocabulary_structure(
        self,
    ):

        for entry in VOCABULARY:

            self.assertEqual(
                len(entry),
                8,
            )

            for value in entry:

                self.assertIsInstance(
                    value,
                    str,
                )

    def test_languages(
        self,
    ):

        self.assertEqual(
            set(LANGUAGES.keys()),
            {
                "English",
                "German",
                "Spanish",
                "French",
                "Japanese",
                "Russian",
            },
        )

    def test_english_levels(
        self,
    ):

        self.assertEqual(
            LANGUAGES["English"]["levels"],
            [
                "A1",
                "A2",
                "B1",
                "B2",
                "C1",
            ],
        )

    def test_russian_levels(
        self,
    ):

        self.assertEqual(
            LANGUAGES["Russian"]["levels"],
            [
                "A1",
                "A2",
                "B1",
                "B2",
                "C1",
            ],
        )

    def test_japanese_levels(
        self,
    ):

        self.assertEqual(
            LANGUAGES["Japanese"]["levels"],
            [
                "N5",
                "N4",
                "N3",
                "N2",
                "N1",
            ],
        )

    def test_cumulative_english_decks(
        self,
    ):

        a1 = len(
            build_deck(
                "English",
                "A1",
            )
        )

        a2 = len(
            build_deck(
                "English",
                "A2",
            )
        )

        b1 = len(
            build_deck(
                "English",
                "B1",
            )
        )

        b2 = len(
            build_deck(
                "English",
                "B2",
            )
        )

        c1 = len(
            build_deck(
                "English",
                "C1",
            )
        )

        self.assertGreater(
            a2,
            a1,
        )

        self.assertGreater(
            b1,
            a2,
        )

        self.assertGreater(
            b2,
            b1,
        )

        self.assertGreater(
            c1,
            b2,
        )

    def test_cumulative_russian_decks(
        self,
    ):

        a1 = len(
            build_deck(
                "Russian",
                "A1",
            )
        )

        a2 = len(
            build_deck(
                "Russian",
                "A2",
            )
        )

        b1 = len(
            build_deck(
                "Russian",
                "B1",
            )
        )

        b2 = len(
            build_deck(
                "Russian",
                "B2",
            )
        )

        c1 = len(
            build_deck(
                "Russian",
                "C1",
            )
        )

        self.assertGreater(
            a2,
            a1,
        )

        self.assertGreater(
            b1,
            a2,
        )

        self.assertGreater(
            b2,
            b1,
        )

        self.assertGreater(
            c1,
            b2,
        )

    def test_russian_deck(
        self,
    ):

        deck = build_deck(
            "Russian",
            "A1",
        )

        self.assertGreater(
            len(deck),
            0,
        )

        first = deck[0]

        self.assertEqual(
            len(first),
            7,
        )

        self.assertEqual(
            first[0],
            "привет",
        )

        self.assertEqual(
            first[1],
            "hello",
        )

        self.assertEqual(
            first[2],
            "hallo",
        )

        self.assertEqual(
            first[3],
            "hola",
        )

        self.assertEqual(
            first[4],
            "bonjour",
        )

        self.assertEqual(
            first[5],
            "こんにちは",
        )

        self.assertEqual(
            first[6],
            "привет",
        )

    def test_english_deck(
        self,
    ):

        deck = build_deck(
            "English",
            "A1",
        )

        first = deck[0]

        self.assertEqual(
            first[0],
            "hello",
        )

        self.assertEqual(
            first[1],
            "hello",
        )

        self.assertEqual(
            first[2],
            "hallo",
        )

        self.assertEqual(
            first[3],
            "hola",
        )

        self.assertEqual(
            first[4],
            "bonjour",
        )

        self.assertEqual(
            first[5],
            "こんにちは",
        )

        self.assertEqual(
            first[6],
            "привет",
        )

    def test_deck_parser(
        self,
    ):

        self.assertEqual(
            parse_deck_name(
                "English C1"
            ),
            (
                "English",
                "C1",
            ),
        )

        self.assertEqual(
            parse_deck_name(
                "Japanese N1"
            ),
            (
                "Japanese",
                "N1",
            ),
        )

        self.assertEqual(
            parse_deck_name(
                "Russian C1"
            ),
            (
                "Russian",
                "C1",
            ),
        )

    def test_deck_count(
        self,
    ):

        self.assertEqual(
            len(get_all_decks()),
            30,
        )

    def test_sm2_first_review(
        self,
    ):

        result = calculate_next_review(
            4,
            0,
            0,
            2.5,
        )

        self.assertEqual(
            result[0],
            1,
        )

        self.assertEqual(
            result[1],
            1,
        )

    def test_sm2_second_review(
        self,
    ):

        result = calculate_next_review(
            4,
            1,
            1,
            2.5,
        )

        self.assertEqual(
            result[0],
            2,
        )

        self.assertEqual(
            result[1],
            6,
        )

    def test_failed_review(
        self,
    ):

        result = calculate_next_review(
            0,
            5,
            30,
            2.5,
        )

        self.assertEqual(
            result[0],
            0,
        )

        self.assertEqual(
            result[3],
            1,
        )


def run_tests():

    unittest.main(
        argv=[
            "flash_cards_bot.py",
        ],
        verbosity=2,
    )


# ============================================================
# START BOT
# ============================================================

async def run_bot():

    global current_bot

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )

    init_database()

    migrate_database()

    current_bot = Bot(
        token=BOT_TOKEN
    )

    cleanup_task = asyncio.create_task(
        session_cleanup_loop()
    )

    logger.info(
        "Flashcards bot started."
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

        await asyncio.gather(
            cleanup_task,
            return_exceptions=True,
        )

        await current_bot.session.close()

        current_bot = None

        logger.info(
            "Flashcards bot stopped."
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in tests.",
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
