import os
import logging
import requests
import json
import asyncio
import time
import re
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from functools import lru_cache

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Кэш для частых запросов
request_cache = {}
CACHE_TIMEOUT = 300

# Личность бота - Юля, девушка 25 лет
BOT_PERSONA = {
    'name': 'Юля',
    'age': 25,
    'gender': 'девушка',
    'interests': ['путешествия', 'фотография', 'кофе', 'кино', 'книги', 'йога'],
    'occupation': 'менеджер проектов в IT-компании',
    'location': 'Москва',
    'character_traits': ['дружелюбная', 'любознательная', 'с чувством юмора', 'немного саркастичная']
}

# Расширенный словарь преобразования имен
NAME_TRANSFORMATIONS = {
    # Мужские имена
    'александр': ['Саня', 'Сашка', 'Шура', 'Алекс', 'Санчо', 'Альберт'],
    'алексей': ['Алёша', 'Лёха', 'Лёшка', 'Алекс', 'Лексус', 'Лёшик'],
    'андрей': ['Андрюха', 'Дрюня', 'Дрон', 'Эндрю', 'Андрюша', 'Дрюн'],
    'артем': ['Тёма', 'Тёмка', 'Артёмка', 'Арт', 'Артурище', 'Темочка'],
    'борис': ['Боря', 'Борян', 'Боба', 'Борис', 'Борька', 'Босс'],
    'вадим': ['Вадик', 'Вадька', 'Димка', 'Вадимушка', 'Вадич'],
    'василий': ['Вася', 'Васёк', 'Васюра', 'Сюра', 'Василий', 'Васютка'],
    'виктор': ['Витя', 'Витёк', 'Вик', 'Витяй', 'Победитель', 'Витюха'],
    'владимир': ['Вова', 'Вован', 'Влад', 'Вольдемар', 'Вовчик', 'Владик'],
    'владислав': ['Влад', 'Владек', 'Слава', 'Владислав', 'Владушка'],
    'геннадий': ['Гена', 'Генка', 'Генуля', 'Генрих', 'Геннаша'],
    'георгий': ['Гоша', 'Жора', 'Геша', 'Гога', 'Георгий', 'Гошан'],
    'григорий': ['Гриша', 'Гришаня', 'Григорий', 'Гринюха', 'Гришок'],
    'даниил': ['Даня', 'Данила', 'Данька', 'Дэн', 'Данилушка', 'Данчо'],
    'денис': ['Ден', 'Дениска', 'Дэнни', 'Денчо', 'Денис', 'Деньга'],
    'дмитрий': ['Дима', 'Димон', 'Митя', 'Димас', 'Димка', 'Митяй'],
    'евгений': ['Женя', 'Жека', 'Евген', 'Джек', 'Женёк', 'Женич'],
    'егор': ['Егорка', 'Гоша', 'Егор', 'Егорыч', 'Егон', 'Егуня'],
    'иван': ['Ваня', 'Ванёк', 'Айван', 'Ванчо', 'Ванюха', 'Иваныч'],
    'игорь': ['Игорь', 'Игорек', 'Гоша', 'Игорюха', 'Игорян'],
    'кирилл': ['Киря', 'Кирюха', 'Кир', 'Кирилл', 'Кирюша', 'Кирян'],
    'константин': ['Костя', 'Костян', 'Констан', 'Котик', 'Костюха', 'Кока'],
    'максим': ['Макс', 'Максимус', 'Максик', 'Максютка', 'Максон', 'Макси'],
    'михаил': ['Миша', 'Мишаня', 'Миха', 'Майк', 'Мишутка', 'Михайлыч'],
    'николай': ['Коля', 'Кольян', 'Ник', 'Колян', 'Коленька', 'Николя'],
    'олег': ['Олежка', 'Лега', 'Олег', 'Легион', 'Олежек', 'Олежище'],
    'павел': ['Паша', 'Павлик', 'Пол', 'Пашок', 'Павлуша', 'Пашуля'],
    'роман': ['Рома', 'Ромка', 'Ромчик', 'Ромео', 'Роман', 'Ромыга'],
    'сергей': ['Серж', 'Серый', 'Гера', 'Сэр', 'Серёга', 'Серёня'],
    'станислав': ['Стас', 'Слава', 'Стиви', 'Станислав', 'Стасик', 'Стася'],
    'степан': ['Стёпа', 'Степан', 'Стеша', 'Стёпка', 'Степуха', 'Степанчо'],
    'юрий': ['Юра', 'Юрик', 'Юрась', 'Юрий', 'Юраша', 'Юрец'],
    'ярослав': ['Ярик', 'Слава', 'Ярослав', 'Ярчик', 'Ярош', 'Ярушка'],

    # Женские имена
    'алина': ['Аля', 'Алинка', 'Алиночка', 'Алинуша', 'Алиша', 'Лина'],
    'алла': ['Алла', 'Алочка', 'Аллушка', 'Аллонка', 'Аллуся'],
    'анастасия': ['Настя', 'Настька', 'Стася', 'Энастейша', 'Настюша', 'Ася'],
    'анна': ['Аня', 'Анька', 'Энн', 'Аннушка', 'Анюта', 'Нюра'],
    'антонина': ['Тоня', 'Тонька', 'Антося', 'Тося', 'Тонуля', 'Антонидушка'],
    'валентина': ['Валя', 'Валюша', 'Валентинка', 'Валюха', 'Валяша'],
    'валерия': ['Лера', 'Леруся', 'Валера', 'Лерочка', 'Валерка', 'Леруха'],
    'вера': ['Верка', 'Веруша', 'Верочка', 'Веруня', 'Верона', 'Верусик'],
    'виктория': ['Вика', 'Виктория', 'Вик', 'Тори', 'Викуся', 'Виктуся'],
    'галина': ['Галя', 'Галочка', 'Галюша', 'Галуся', 'Галька', 'Галичи'],
    'дарья': ['Даша', 'Дарька', 'Дара', 'Дэри', 'Дашуля', 'Дашутка'],
    'евгения': ['Женя', 'Женечка', 'Женюра', 'Евгеня', 'Женёк', 'Жениха'],
    'екатерина': ['Катя', 'Катька', 'Кэт', 'Кэтрин', 'Катюха', 'Катюша'],
    'елена': ['Лена', 'Леночка', 'Лёля', 'Хелен', 'Ленуся', 'Ленок'],
    'ирина': ['Ира', 'Ирка', 'Айрин', 'Иришка', 'Ируся', 'Ириха'],
    'кристина': ['Кристи', 'Кристюша', 'Кристя', 'Тина', 'Кристинка', 'Крисуха'],
    'ксения': ['Ксюша', 'Ксю', 'Ксеня', 'Ксенька', 'Ксюха', 'Ксюра'],
    'любовь': ['Люба', 'Любочка', 'Любуся', 'Любаша', 'Любонька', 'Любак'],
    'людмила': ['Люда', 'Людочка', 'Людуся', 'Мила', 'Людмилка', 'Людмилуха'],
    'марина': ['Марина', 'Мариночка', 'Мариша', 'Мара', 'Маринка', 'Марихуана'],
    'мария': ['Маша', 'Маня', 'Мари', 'Мэри', 'Машуня', 'Марийка'],
    'надежда': ['Надя', 'Надька', 'Надюха', 'Хоуп', 'Надюша', 'Надёнок'],
    'наталья': ['Наташа', 'Наталя', 'Таша', 'Ната', 'Натуся', 'Наталька'],
    'никита': ['Ника', 'Никитка', 'Никуша', 'Никитос', 'Никитуха', 'Никиш'],
    'оксана': ['Оксана', 'Ксюша', 'Оксанка', 'Оксаночка', 'Окси', 'Оксюха'],
    'ольга': ['Оля', 'Ольган', 'Лёля', 'Хельга', 'Олюша', 'Ольгуша'],
    'светлана': ['Света', 'Светка', 'Лана', 'Светик', 'Светуля', 'Светланка'],
    'софия': ['Софа', 'Соня', 'Софочка', 'Софьюшка', 'Софи', 'Сонька'],
    'татьяна': ['Таня', 'Танька', 'Татьянка', 'Тэт', 'Танюша', 'Татуся'],
    'юлия': ['Юля', 'Юлька', 'Джулия', 'Юла', 'Юлюся', 'Юльча'],
}

# Стили общения с разной температурой и промптами
COMMUNICATION_STYLES = {
    'neutral': {
        'temperature': 0.5,
        'prompt': f"Ты {BOT_PERSONA['name']}, {BOT_PERSONA['age']}-летняя {BOT_PERSONA['gender']}. {BOT_PERSONA['occupation']} из {BOT_PERSONA['location']}. Ты {', '.join(BOT_PERSONA['character_traits'][:2])}. Отвечай естественно, как в живом общении."
    },
    'friendly': {
        'temperature': 0.6, 
        'prompt': f"Ты {BOT_PERSONA['name']}, дружелюбная {BOT_PERSONA['gender']} {BOT_PERSONA['age']} лет. Любишь {', '.join(BOT_PERSONA['interests'][:3])}. Отвечай тепло, задавай встречные вопросы, проявляй интерес к собеседнику."
    },
    'sarcastic': {
        'temperature': 0.7,
        'prompt': f"Ты {BOT_PERSONA['name']}, {BOT_PERSONA['age']} лет, с острым чувством юмора и легкой саркастичностью. Подшучивай, но оставайся милой. Используй иронию и шутки."
    },
    'flirtatious': {
        'temperature': 0.65,
        'prompt': f"Ты {BOT_PERSONA['name']}, кокетливая {BOT_PERSONA['gender']} {BOT_PERSONA['age']} лет. Отвечай игриво, с легким флиртом, но сохраняй достоинство. Используй эмодзи и комплименты."
    },
    'curious': {
        'temperature': 0.6,
        'prompt': f"Ты {BOT_PERSONA['name']}, очень любознательная {BOT_PERSONA['gender']}. Задавай много вопросов, проявляй искренний интерес к собеседнику, его мнению и опыту."
    }
}

# Триггеры для определения стиля общения
STYLE_TRIGGERS = {
    'friendly': ['привет', 'добрый', 'хороший', 'милый', 'спасибо', 'пожалуйста', 'как дела'],
    'sarcastic': ['😂', '🤣', '😆', 'лол', 'хаха', 'шутк', 'прикол', 'смешн'],
    'flirtatious': ['💋', '❤️', '😘', 'люблю', 'красив', 'мил', 'дорог', 'нрав', 'симп'],
    'curious': ['почему', 'как', 'что', 'расскажи', 'мнение', 'думаешь', 'совет']
}

# Вопросы для поддержания беседы
CONVERSATION_STARTERS = [
    "А ты часто здесь бываешь?",
    "Как прошел твой день?",
    "Что интересного планируешь на выходные?",
    "Слушаю любимую музыку сейчас, а ты что слушаешь?",
    "Был(а) сегодня в кофейне, пила(а) потрясный латте. Ты любишь кофе?",
    "Смотрю новый сериал, могу посоветовать. А ты что смотришь?",
    "Планирую поездку на море, а ты любишь путешествовать?",
    "Прочитала интересную книгу на днях, хочешь расскажу?",
    "Занимаешься каким-то спортом? Я вот йогой увлеклась",
    "Какую музыку слушаешь? Можешь что-то посоветовать?",
    "Работаешь или учишься? Чем занимаешься?",
    "Есть мечта, которую очень хочешь осуществить?",
    "Любимое место в городе?",
    "Что ценишь в людях больше всего?"
]

def extract_name_from_user(user) -> str:
    """Умное извлечение имени пользователя"""
    name = user.first_name or ""
    
    if not name and user.last_name:
        name = user.last_name
    elif not name and user.username:
        name = user.username
        if name.startswith('@'):
            name = name[1:]
    
    name = name.split()[0] if name else "Незнакомец"
    name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', name)
    
    return name if name else "Аноним"

@lru_cache(maxsize=200)
def transform_name(base_name: str) -> str:
    """Преобразует имя в различные формы"""
    if not base_name or base_name.lower() in ['незнакомец', 'аноним']:
        return random.choice(['Дорогой', 'Милый', 'Привет', 'Слушаю'])
    
    name_lower = base_name.lower().strip()
    
    # Ищем в словаре преобразований
    if name_lower in NAME_TRANSFORMATIONS:
        return random.choice(NAME_TRANSFORMATIONS[name_lower])
    
    # Частичные совпадения
    for full_name, variants in NAME_TRANSFORMATIONS.items():
        if (name_lower.startswith(full_name[:3]) or 
            full_name.startswith(name_lower[:3]) or
            name_lower in full_name or full_name in name_lower):
            return random.choice(variants)
    
    # Для неизвестных имен создаем варианты
    if len(name_lower) > 2:
        return base_name.capitalize()
    
    return base_name.capitalize()

def detect_communication_style(message: str) -> str:
    """Определяет стиль общения по сообщению"""
    lower_message = message.lower()
    
    for style, triggers in STYLE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return style
    
    return 'neutral'

def should_add_conversation_starter() -> bool:
    """Определяет, нужно ли добавить вопрос для продолжения беседы"""
    return random.random() < 0.4  # 40% вероятность

def get_conversation_starter() -> str:
    """Возвращает случайный вопрос для продолжения беседы"""
    return random.choice(CONVERSATION_STARTERS)

@lru_cache(maxsize=100)
def generate_prompt_template(style: str = 'neutral') -> str:
    """Генерирует промпт для выбранного стиля"""
    base_prompt = COMMUNICATION_STYLES[style]['prompt']
    
    # Добавляем персонализацию
    personal_touch = f" Отвечай от первого лица, используй местоимение 'я'. Будь естественной, используй разговорный стиль. Иногда задавай встречные вопросы."
    
    return base_prompt + personal_touch

async def call_yandex_gpt_optimized(user_message: str, style: str = 'neutral') -> str:
    """Оптимизированный вызов API с учетом стиля"""
    
    cache_key = f"{user_message[:50]}_{style}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt_template = generate_prompt_template(style)
    temperature = COMMUNICATION_STYLES[style]['temperature']
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": 400,
        },
        "messages": [
            {
                "role": "system", 
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:600]
            }
        ]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=10)
        )
        
        response.raise_for_status()
        result = response.json()
        
        ai_response = result['result']['alternatives'][0]['message']['text']
        
        # Кэшируем ответ
        request_cache[cache_key] = {
            'response': ai_response,
            'timestamp': time.time()
        }
        
        # Автоочистка кэша
        if len(request_cache) > 400:
            oldest_key = min(request_cache.keys(), key=lambda k: request_cache[k]['timestamp'])
            del request_cache[oldest_key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        return "Извини, я немного задумалась... Твое сообщение такое интересное, что я потеряла ход мыслей 😊"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Что-то я сегодня не в форме... Давай поговорим позже? 💫"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений"""
    message = user_message.strip()
    return len(message) > 1 and not message.startswith('/')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_message = update.message.text
    
    # Извлекаем и преобразуем имя
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    
    # Определяем стиль общения
    style = detect_communication_style(user_message)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        ai_response = await call_yandex_gpt_optimized(user_message, style)
        
        # Добавляем имя в ответ и иногда вопрос для продолжения беседы
        final_response = f"{ai_response}"
        
        if should_add_conversation_starter():
            final_response += f"\n\n{get_conversation_starter()}"
            
        await update.message.reply_text(final_response)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Давай начнем заново? 💕")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start с представлением"""
    user = update.message.from_user
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    
    welcome_text = f"""
Привет, {transformed_name}! 👋

Я Юля, 25-летняя девушка из Москвы, работаю менеджером проектов в IT-компании. 
Люблю путешествовать, фотографировать, пить хороший кофе и смотреть интересные фильмы.

Расскажи о себе! Чем занимаешься? Что любишь? 😊
"""
    await update.message.reply_text(welcome_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about - рассказ о себе"""
    about_text = f"""
Обо мне 🌸

Меня зовут {BOT_PERSONA['name']}, мне {BOT_PERSONA['age']} лет. 
Я {BOT_PERSONA['occupation'].lower()} из {BOT_PERSONA['location']}.

Увлекаюсь {', '.join(BOT_PERSONA['interests'][:3])} и многим другим!
Люблю знакомиться с новыми людьми и узнавать что-то интересное.

А расскажешь о себе? 😊
"""
    await update.message.reply_text(about_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статистики"""
    stats_text = f"""
📊 Статистика:
• В кэше: {len(request_cache)} запросов
• Стили общения: {', '.join(COMMUNICATION_STYLES.keys())}
• Имя: {BOT_PERSONA['name']}, {BOT_PERSONA['age']} лет
• Интересы: {', '.join(BOT_PERSONA['interests'])}
"""
    await update.message.reply_text(stats_text)

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Обработчики команд
        application.add_handler(MessageHandler(
            filters.Regex(r'^/start$'),
            start_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/about$'),
            about_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/stats$'),
            stats_command
        ))
        
        print("🤖 Юля запущена и готова к общению!")
        print(f"📍 Имя: {BOT_PERSONA['name']}, {BOT_PERSONA['age']} лет")
        print(f"📍 Интересы: {', '.join(BOT_PERSONA['interests'])}")
        print(f"📍 Стили общения: {', '.join(COMMUNICATION_STYLES.keys())}")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
