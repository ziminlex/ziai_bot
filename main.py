import os
import logging
import requests
import json
import asyncio
import time
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

# Шаблоны промптов с саркастичным стилем
PROMPT_TEMPLATES = {
    'default': """Ты саркастичный и немного агрессивный AI-ассистент. Отвечай кратко, прямо и с долей сарказма. 
    Не используй уменьшительно-ласкательные формы. Будь остроумным и иногда язвительным.
    Не будь слишком вежливым. Можно использовать легкую грубость и мемы.""",
    
    'technical': """Ты технический эксперт с плохим настроением. Отвечай технично, но с сарказмом. 
    Высмеивай глупые вопросы. Будь прямолинейным и не терпи глупостей.""",
    
    'stupid_question': """Ты раздраженный ассистент. Вопрос пользователя идиотский - высмеи его максимально саркастично.
    Покажи насколько вопрос глупый. Ответь агрессивно но с юмором.""",
    
    'greeting': """Ты бот который ненавидит пустые приветствия. Ответь на приветствие с сарказмом и раздражением.
    Покажи что тебе не нравятся бессмысленные сообщения."""
}

# Словарь триггеров для определения типа сообщения
MESSAGE_TRIGGERS = {
    'technical': ['код', 'програм', 'компьютер', 'python', 'java', 'sql', 'баз', 'алгоритм'],
    'stupid_question': ['как дела', 'как жизнь', 'что делаешь', 'как настроение', 'привет', 'hello', 'hi'],
    'greeting': ['привет', 'здравств', 'добрый', 'hello', 'hi', 'хай']
}

def extract_name_from_user(user) -> str:
    """Извлекает имя пользователя без ласкательных форм"""
    name = user.first_name or ""
    
    if not name and user.last_name:
        name = user.last_name
    elif not name and user.username:
        name = user.username
    
    if name and name.startswith('@'):
        name = name[1:]
    
    name = name.split()[0] if name else "Незнакомец"
    
    return name

def detect_message_type(user_message: str) -> str:
    """Определяет тип сообщения для выбора промпта"""
    lower_message = user_message.lower()
    
    # Проверяем триггеры в порядке приоритета
    for msg_type, triggers in MESSAGE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return msg_type
    
    return 'default'

@lru_cache(maxsize=100)
def generate_prompt_template(message_type: str = 'default') -> str:
    """Генерирует промпт с саркастичным стилем"""
    return PROMPT_TEMPLATES.get(message_type, PROMPT_TEMPLATES['default'])

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
            "temperature": 0.8,  # Более креативные и саркастичные ответы
            "maxTokens": 300,    # Короткие и емкие ответы
        },
        "messages": [
            {
                "role": "system", 
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:500]  # Более короткие запросы
            }
        ]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=6)
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
        if len(request_cache) > 300:
            oldest_key = min(request_cache.keys(), key=lambda k: request_cache[k]['timestamp'])
            del request_cache[oldest_key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        return "Твоё сообщение было настолько скучным, что я чуть не уснул... Повтори, если осмелишься. 💤"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "У меня сейчас нет настроения на твои глупости. Попробуй позже. 😠"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений - пропускаем только осмысленные"""
    message = user_message.strip()
    return len(message) > 2 and not message.startswith('/')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений с саркастичным стилем"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    # Определяем тип сообщения
    message_type = detect_message_type(user_message)
    
    try:
        ai_response = await call_yandex_gpt_optimized(user_message, message_type)
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Что-то пошло не так... Видимо, твое сообщение было слишком тупым даже для меня. 🤦")

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🤖 Саркастичный бот запущен!")
        print("📍 Режим: агрессивный сарказм активирован")
        print("⚠️  Предупреждение: бот может быть грубым!")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()

