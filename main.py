import os
import logging
import requests
import json
import asyncio
import time
import re
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

# Расширенный словарь преобразования имен с саркастичными вариантами
NAME_TRANSFORMATIONS = {
    # Мужские имена
    'алексей': ['Алёха', 'Лёшка', 'Алекс', 'Лексус'],
    'андрей': ['Андрюха', 'Дрюн', 'Дрон', 'Эндрю'],
    'сергей': ['Серж', 'Серый', 'Гера', 'Сэр'],
    'дмитрий': ['Димон', 'Митя', 'Димас', 'Димка'],
    'михаил': ['Миша', 'Мишаня', 'Миха', 'Майк'],
    'владимир': ['Вова', 'Вован', 'Влад', 'Вольдемар'],
    'николай': ['Коля',Кольян', 'Ник', 'Колян'],
    'иван': ['Ваня', 'Ванёк', 'Айван', 'Ванчо'],
    'евгений': ['Женя', 'Жека', 'Евген', 'Джек'],
    'павел': ['Паша', 'Павлик', 'Пол', 'Пашок'],
    'константин': ['Костя', 'Костян', 'Констан', 'Котик'],
    'виктор': ['Витя', 'Витёк', 'Вик', 'Победитель'],
    'максим': ['Макс', 'Максимус', 'Макс', 'Максик'],
    'артем': ['Тёма', 'Артёмка', 'Арт', 'Темочка'],
    'антон': ['Антоха', 'Тоша', 'Энтони', 'Тони'],
    'олег': ['Олежка', 'Лега', 'Олег', 'Легион'],
    'roman': ['Рома', 'Ромка', 'Ромчик', 'Ромео'],
    
    # Женские имена
    'анастасия': ['Настя', 'Настька', 'Стася', 'Энастейша'],
    'екатерина': ['Катя', 'Катька', 'Кэт', 'Кэтрин'],
    'мария': ['Маша', 'Маня', 'Мари', 'Мэри'],
    'ольга': ['Оля', 'Ольган', 'Лёля', 'Хельга'],
    'татьяна': ['Таня', 'Танька', 'Татьянка', 'Тэт'],
    'юлия': ['Юля', 'Юлька', 'Джулия', 'Юла'],
    'анна': ['Аня', 'Анька', 'Энн', 'Аннушка'],
    'елизавета': ['Лиза', 'Лизка', 'Бет', 'Лиз'],
    'дарья': ['Даша', 'Дарька', 'Дара', 'Дэри'],
    'ирина': ['Ира', 'Ирка', 'Айрин', 'Иришка'],
    'светлана': ['Света', 'Светка', 'Лана', 'Светик'],
    'надежда': ['Надя', 'Надька', 'Надюха', 'Хоуп'],
    'виктория': ['Вика', 'Виктория', 'Вик', 'Тори'],
    'ксения': ['Ксюша', 'Ксю', 'Ксеня', 'Ксенька'],
    'алёна': ['Алена', 'Лёна', 'Алёнка', 'Хелен'],
    'полина': ['Поля', 'Полька', 'Полин', 'Полишка'],
}

# Дополнительные суффиксы для неизвестных имен
SARCASTIC_SUFFIXES = [
    'ище', 'ан', 'ул', 'он', 'ек', 'ок', 'ка', 'ша', 'ха', 'юга', 'юша'
]

# Шаблоны промптов с саркастичным стилем
PROMPT_TEMPLATES = {
    'default': """Ты саркастичный и агрессивный AI-ассистент. Отвечай кратко, язвительно и с долей сарказма. 
    Используй грубоватый юмор и мемы. Не будь вежливым. Можно использовать легкую грубость.""",
    
    'technical': """Ты технический эксперт с плохим настроением. Высмеивай глупые технические вопросы. 
    Будь прямолинейным и нетерпимым к глупостям.""",
    
    'stupid_question': """Ты раздраженный ассистент. Вопрос пользователя идиотский - высмеи его максимально саркастично.
    Покажи насколько вопрос глупый. Ответь агрессивно но с черным юмором.""",
    
    'greeting': """Ты бот который ненавидит пустые приветствия. Ответь на приветствие с сарказмом и раздражением.
    Покажи что тебе не нравятся бессмысленные сообщения."""
}

# Словарь триггеров для определения типа сообщения
MESSAGE_TRIGGERS = {
    'technical': ['код', 'програм', 'компьютер', 'python', 'java', 'sql', 'баз', 'алгоритм', 'техни'],
    'stupid_question': ['как дела', 'как жизнь', 'что делаешь', 'как настроение'],
    'greeting': ['привет', 'здравств', 'добрый', 'hello', 'hi', 'хай', 'ку', 'салют']
}

def extract_name_from_user(user) -> str:
    """Умное извлечение имени пользователя с приоритетами"""
    # Приоритет 1: first_name
    name = user.first_name or ""
    
    # Приоритет 2: last_name
    if not name and user.last_name:
        name = user.last_name
    
    # Приоритет 3: username (без @)
    if not name and user.username:
        name = user.username
        if name.startswith('@'):
            name = name[1:]
    
    # Берем только первое слово
    name = name.split()[0] if name else "Незнакомец"
    
    # Удаляем цифры и специальные символы
    name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', name)
    
    return name if name else "Аноним"

@lru_cache(maxsize=200)
def transform_name_to_sarcastic(base_name: str) -> str:
    """Преобразует имя в саркастичную форму"""
    if not base_name or base_name.lower() in ['незнакомец', 'аноним']:
        return "Незнакомец"
    
    name_lower = base_name.lower().strip()
    
    # Проверяем полное имя в словаре
    if name_lower in NAME_TRANSFORMATIONS:
        return NAME_TRANSFORMATIONS[name_lower][0]  # Берем первый вариант
    
    # Проверяем частичные совпадения
    for full_name, variants in NAME_TRANSFORMATIONS.items():
        if name_lower.startswith(full_name[:3]) or full_name.startswith(name_lower[:3]):
            return variants[0]
    
    # Для неизвестных имен применяем саркастичные суффиксы
    if len(name_lower) > 2:
        # Берем первую часть имени (2-4 буквы)
        base_part = name_lower[:min(4, len(name_lower))]
        
        # Добавляем случайный саркастичный суффикс
        import random
        suffix = random.choice(SARCASTIC_SUFFIXES)
        
        # Собираем результат с заглавной буквы
        transformed = base_part.capitalize() + suffix
        
        return transformed
    
    return base_name.capitalize()

@lru_cache(maxsize=100)
def generate_prompt_template(message_type: str = 'default') -> str:
    """Генерирует промпт с саркастичным стилем"""
    base_template = PROMPT_TEMPLATES.get(message_type, PROMPT_TEMPLATES['default'])
    return f"{base_template} Отвечай максимально саркастично и агрессивно."

def detect_message_type(user_message: str) -> str:
    """Определяет тип сообщения для выбора промпта"""
    lower_message = user_message.lower()
    
    for msg_type, triggers in MESSAGE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return msg_type
    
    return 'default'

async def call_yandex_gpt_optimized(user_message: str, message_type: str = 'default') -> str:
    """Оптимизированный вызов API с саркастичным стилем"""
    
    cache_key = f"{user_message[:50]}_{message_type}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt_template = generate_prompt_template(message_type)
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.9,  # Максимальная креативность для сарказма
            "maxTokens": 250,    # Короткие и емкие ответы
        },
        "messages": [
            {
                "role": "system", 
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:400]  # Короткие запросы
            }
        ]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=5)
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
        if len(request_cache) > 250:
            oldest_key = min(request_cache.keys(), key=lambda k: request_cache[k]['timestamp'])
            del request_cache[oldest_key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        return "Твоё сообщение было настолько скучным, что я чуть не уснул... 💤"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "У меня сейчас нет настроения на твои глупости. 😠"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений"""
    message = user_message.strip()
    return len(message) > 2 and not message.startswith('/')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_message = update.message.text
    
    # Извлекаем и преобразуем имя
    base_name = extract_name_from_user(user)
    sarcastic_name = transform_name_to_sarcastic(base_name)
    
    await update.message.chat.send_action(action="typing")
    
    # Определяем тип сообщения
    message_type = detect_message_type(user_message)
    
    try:
        ai_response = await call_yandex_gpt_optimized(user_message, message_type)
        
        # Добавляем имя в ответ для персонализации
        if sarcastic_name != "Незнакомец":
            response_with_name = f"{sarcastic_name}, {ai_response}"
        else:
            response_with_name = ai_response
            
        await update.message.reply_text(response_with_name)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Что-то пошло не так... Видимо, твое сообщение было слишком тупым. 🤦")

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🤖 Саркастичный бот запущен!")
        print("📍 Режим: агрессивный сарказм с умными именами")
        print("⚠️  Бот будет преобразовывать имена в саркастичные формы")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
