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
CACHE_TIMEOUT = 300  # 5 минут

# Статистика использования
api_stats = {
    'total_requests': 0,
    'failed_requests': 0,
    'last_request_time': None
}

# Шаблоны промптов
PROMPT_TEMPLATES = {
    'default': "Ты полезный AI-ассистент. Отвечай кратко и по делу.",
    'friendly': "Ты дружелюбный помощник. Отвечай тепло и обстоятельно.",
    'technical': "Ты технический эксперт. Давай точные и лаконичные ответы."
}

@lru_cache(maxsize=100)
def generate_prompt_template(user_name: str, message_type: str = 'default') -> str:
    """Генерирует промпт с кэшированием"""
    base_template = PROMPT_TEMPLATES.get(message_type, PROMPT_TEMPLATES['default'])
    return f"{base_template} Тебе пишет {user_name}."

async def call_yandex_gpt(user_message: str, user_name: str, message_type: str = 'default') -> str:
    """Оптимизированный вызов Yandex GPT API"""
    
    # Проверка кэша
    cache_key = f"{user_message}_{message_type}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    # Подготовка запроса
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt_template = generate_prompt_template(user_name, message_type)
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.4,  # Более консервативные ответы
            "maxTokens": 512,    # Ограничение длины
            "top_p": 0.8
        },
        "messages": [
            {
                "role": "system", 
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:1000]  # Ограничение длины запроса
            }
        ]
    }
    
    try:
        # Асинхронный запрос
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=10)
        )
        
        api_stats['total_requests'] += 1
        api_stats['last_request_time'] = datetime.now()
        
        response.raise_for_status()
        result = response.json()
        
        ai_response = result['result']['alternatives'][0]['message']['text']
        
        # Сохранение в кэш
        request_cache[cache_key] = {
            'response': ai_response,
            'timestamp': time.time()
        }
        
        # Очистка старого кэша
        if len(request_cache) > 1000:
            oldest_key = min(request_cache.keys(), key=lambda k: request_cache[k]['timestamp'])
            del request_cache[oldest_key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        logger.warning("Timeout при запросе к Yandex GPT")
        return "Извините, сервис временно недоступен. Попробуйте позже."
        
    except requests.exceptions.RequestException as e:
        api_stats['failed_requests'] += 1
        logger.error(f"Ошибка сети: {e}")
        return "Ошибка соединения. Попробуйте еще раз."
        
    except Exception as e:
        api_stats['failed_requests'] += 1
        logger.error(f"Ошибка API: {e}")
        return "Произошла ошибка при обработке запроса."

def should_process_message(user_message: str) -> bool:
    """Проверяет, стоит ли обрабатывать сообщение"""
    # Игнорируем очень короткие сообщения
    if len(user_message.strip()) < 2:
        return False
        
    # Игнорируем команды
    if user_message.startswith('/'):
        return False
        
    return True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оптимизированный обработчик сообщений"""
    user = update.message.from_user
    user_message = update.message.text
    
    if not should_process_message(user_message):
        return
    
    # Получаем имя пользователя
    user_name = user.first_name or "Друг"
    if user.last_name:
        user_name = f"{user.first_name} {user.last_name}"
    
    # Показываем статус "печатает..."
    await update.message.chat.send_action(action="typing")
    
    # Определяем тип сообщения для оптимизации промпта
    message_type = 'default'
    if any(word in user_message.lower() for word in ['техни', 'код', 'програм']):
        message_type = 'technical'
    elif any(word in user_message.lower() for word in ['привет', 'как дела', 'настроен']):
        message_type = 'friendly'
    
    try:
        # Асинхронный вызов API
        ai_response = await call_yandex_gpt(user_message, user_name, message_type)
        
        # Отправляем ответ
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        await update.message.reply_text("Произошла непредвиденная ошибка.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статистики"""
    stats_text = f"""
📊 Статистика API:
• Всего запросов: {api_stats['total_requests']}
• Неудачных: {api_stats['failed_requests']}
• Последний запрос: {api_stats['last_request_time'] or 'еще не было'}
• В кэше: {len(request_cache)} запросов
"""
    await update.message.reply_text(stats_text)

def main():
    """Запускает оптимизированного бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Обработчик сообщений
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Команда статистики
        application.add_handler(MessageHandler(
            filters.Regex(r'^/stats$'),
            stats_command
        ))
        
        print("🤖 Оптимизированный бот запущен!")
        print("📍 Используются: кэширование, асинхронность, оптимизированные промпты")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()
