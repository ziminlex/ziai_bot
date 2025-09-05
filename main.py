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

# Словарь уменьшительно-ласкательных имен
AFFECTIONATE_NAMES = {
    'алексей': 'Алёша', 'алёша': 'Алёша', 'леша': 'Лёша',
    'андрей': 'Андрюша', 'андрюша': 'Андрюша',
    'сергей': 'Сережа', 'серёжа': 'Серёжа',
    'дмитрий': 'Дима', 'дима': 'Дима',
    'михаил': 'Миша', 'миша': 'Миша',
    'владимир': 'Вова', 'вова': 'Вова',
    'николай': 'Коля', 'коля': 'Коля',
    'иван': 'Ваня', 'ваня': 'Ваня',
    'евгений': 'Женя', 'женя': 'Женя',
    'павел': 'Паша', 'паша': 'Паша',
    'константин': 'Костя', 'костя': 'Костя',
    'виктор': 'Витя', 'витя': 'Витя',
    'анастасия': 'Настя', 'настя': 'Настя',
    'екатерина': 'Катя', 'катя': 'Катя',
    'мария': 'Маша', 'маша': 'Маша',
    'ольга': 'Оля', 'оля': 'Оля',
    'татьяна': 'Таня', 'таня': 'Таня',
    'юлия': 'Юля', 'юля': 'Юля',
    'анна': 'Аня', 'аня': 'Аня',
    'елизавета': 'Лиза', 'лиза': 'Лиза',
    'дарья': 'Даша', 'даша': 'Даша'
}

# Шаблоны промптов с персонализацией
PROMPT_TEMPLATES = {
    'default': "Ты дружелюбный AI-ассистент. Отвечай тепло и заботливо, используй уменьшительно-ласкательные формы имен.",
    'technical': "Ты технический эксперт. Будь точным, но сохраняй дружелюбный тон.",
    'friendly': "Ты лучший друг. Общайся тепло, с эмпатией и заботой."
}

@lru_cache(maxsize=200)
def get_affectionate_name(name: str) -> str:
    """Возвращает уменьшительно-ласкательное имя"""
    if not name:
        return "друг"
    
    name_lower = name.lower().strip()
    
    # Проверяем полное имя
    if name_lower in AFFECTIONATE_NAMES:
        return AFFECTIONATE_NAMES[name_lower]
    
    # Проверяем частичные совпадения
    for full_name, affectionate in AFFECTIONATE_NAMES.items():
        if name_lower in full_name or full_name in name_lower:
            return affectionate
    
    # Для неизвестных имен возвращаем оригинал с уменьшительным суффиксом
    if len(name) > 3:
        if name_lower.endswith(('ий', 'ей', 'ай')):
            return name[:-2] + 'енька'
        elif name_lower.endswith('н'):
            return name + 'юша'
        else:
            return name + 'ша'
    
    return name

def extract_name_from_user(user) -> str:
    """Извлекает и нормализует имя пользователя"""
    # Используем first_name как основной источник
    name = user.first_name or ""
    
    # Если first_name отсутствует, используем last_name или username
    if not name and user.last_name:
        name = user.last_name
    elif not name and user.username:
        name = user.username
    
    # Убираем @ из username если он есть
    if name and name.startswith('@'):
        name = name[1:]
    
    # Берем только первое слово (на случай полного имени)
    name = name.split()[0] if name else "друг"
    
    return name

@lru_cache(maxsize=100)
def generate_prompt_template(base_name: str, message_type: str = 'default') -> str:
    """Генерирует персонализированный промпт"""
    affectionate_name = get_affectionate_name(base_name)
    base_template = PROMPT_TEMPLATES.get(message_type, PROMPT_TEMPLATES['default'])
    
    return f"{base_template} Тебе пишет {affectionate_name}. Обращайся к нему/ней по имени в уменьшительно-ласкательной форме."

async def call_yandex_gpt_optimized(user_message: str, user_name: str, message_type: str = 'default') -> str:
    """Оптимизированный вызов API с кэшированием"""
    
    cache_key = f"{user_message[:50]}_{message_type}_{user_name}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    affectionate_name = get_affectionate_name(user_name)
    prompt_template = generate_prompt_template(user_name, message_type)
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": 400,
        },
        "messages": [
            {
                "role": "system", 
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:800]
            }
        ]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=8)
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
        if len(request_cache) > 500:
            for key in list(request_cache.keys())[:100]:
                del request_cache[key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        return f"{affectionate_name}, я немного подзадумался... Повтори, пожалуйста? 🐢"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return f"{affectionate_name}, у меня небольшие технические сложности. Попробуй еще разок? 💫"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений"""
    message = user_message.strip().lower()
    return len(message) > 1 and not message.startswith('/')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_name = extract_name_from_user(user)
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    # Определяем тип сообщения
    message_type = 'default'
    lower_message = user_message.lower()
    
    if any(word in lower_message for word in ['техни', 'код', 'програм', 'компьютер']):
        message_type = 'technical'
    elif any(word in lower_message for word in ['привет', 'как дела', 'настроен', 'чувств']):
        message_type = 'friendly'
    
    try:
        ai_response = await call_yandex_gpt_optimized(user_message, user_name, message_type)
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        affectionate_name = get_affectionate_name(user_name)
        await update.message.reply_text(f"{affectionate_name}, что-то пошло не так... 😅")

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🤖 Персонализированный бот запущен!")
        print("📍 Обращение по уменьшительно-ласкательным именам активировано")
        
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
