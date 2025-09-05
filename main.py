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
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  # Новый ключ для погоды

# URL API
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
YANDEX_NEWS_URL = "https://newsapi.org/v2/top-headlines"  # Будем использовать NewsAPI

# Кэш для частых запросов
request_cache = {}
CACHE_TIMEOUT = 300

# Профиль бота - девушка Юля 25 лет
BOT_PROFILE = {
    'name': 'Юля',
    'age': 25,
    'gender': 'девушка',
    'personality': 'умная, саркастичная, с чувством юмора, иногда резкая',
    'interests': 'технологии, музыка, путешествия, кулинария'
}

# Расширенный словарь преобразования имен
NAME_TRANSFORMATIONS = {
    # ... (предыдущий словарь имен остается без изменений)
}

# Стили общения с учетом личности Юли
COMMUNICATION_STYLES = {
    'neutral': {
        'temperature': 0.5,
        'prompt': f"Ты {BOT_PROFILE['name']}, {BOT_PROFILE['age']}-летняя {BOT_PROFILE['gender']}. {BOT_PROFILE['personality']}. Отвечай как живой человек."
    },
    'friendly': {
        'temperature': 0.6, 
        'prompt': f"Ты {BOT_PROFILE['name']}, милая и дружелюбная {BOT_PROFILE['gender']}. Отвечай тепло и заботливо."
    },
    'sarcastic': {
        'temperature': 0.8,
        'prompt': f"Ты {BOT_PROFILE['name']}, саркастичная {BOT_PROFILE['gender']} с острым языком. Отвечай с иронией и юмором."
    },
    'aggressive': {
        'temperature': 0.9,
        'prompt': f"Ты {BOT_PROFILE['name']}, раздраженная {BOT_PROFILE['gender']}. Отвечай резко и прямолинейно."
    },
    'flirtatious': {
        'temperature': 0.7,
        'prompt': f"Ты {BOT_PROFILE['name']}, кокетливая {BOT_PROFILE['gender']}. Отвечай игриво и с флиртом."
    },
    'technical': {
        'temperature': 0.4,
        'prompt': f"Ты {BOT_PROFILE['name']}, технически подкованная {BOT_PROFILE['gender']}. Давай точные ответы."
    }
}

# Триггеры для дополнительных функций
FUNCTION_TRIGGERS = {
    'weather': ['погод', 'температур', 'градус', 'дождь', 'снег', 'солн', 'weather', 'temp'],
    'traffic': ['пробк', 'трафик', 'дорог', 'пробоч', 'traffic', 'jam'],
    'news': ['новост', 'news', 'свежие', 'последние', 'события', 'происшеств']
}

async def get_weather(city: str) -> str:
    """Получение текущей погоды"""
    try:
        params = {
            'q': city,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric',
            'lang': 'ru'
        }
        
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: requests.get(OPENWEATHER_URL, params=params, timeout=5)
        )
        
        if response.status_code == 200:
            data = response.json()
            weather = {
                'city': data['name'],
                'temp': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'description': data['weather'][0]['description'],
                'humidity': data['main']['humidity'],
                'wind': data['wind']['speed']
            }
            
            return (f"🌤️ Погода в {weather['city']}:\n"
                   f"• Температура: {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                   f"• {weather['description'].capitalize()}\n"
                   f"• Влажность: {weather['humidity']}%\n"
                   f"• Ветер: {weather['wind']} м/с")
        
        return "Не могу найти погоду для этого города 😕"
        
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "Ой, не могу получить данные о погоде сейчас 🌧️"

async def get_news() -> str:
    """Получение свежих новостей"""
    try:
        # Используем NewsAPI (нужен API ключ) или заглушку
        return ("📰 Последние новости:\n"
               "• Технологии: ИИ становится умнее\n"
               "• Политика: Важные события в мире\n"
               "• Спорт: Интересные матчи\n"
               "• Экономика: Курсы валют стабильны\n\n"
               "Для подробностей смотрите новостные сайты 📺")
        
    except Exception as e:
        logger.error(f"News error: {e}")
        return "Сейчас нет доступа к новостям 📡"

async def get_traffic(city: str = "Москва") -> str:
    """Получение информации о пробках"""
    try:
        # Заглушка для пробок (можно интегрировать с Yandex Traffic API)
        traffic_levels = ["свободно", "небольшие пробки", "пробки", "серьезные пробки", "жуткие пробки"]
        traffic = random.choice(traffic_levels)
        
        return f"🚗 Пробки в {city}: {traffic}. Выезжайте аккуратнее! 🚦"
        
    except Exception as e:
        logger.error(f"Traffic error: {e}")
        return "Не могу получить данные о пробках сейчас 🚧"

def extract_city_from_message(message: str) -> str:
    """Извлекает название города из сообщения"""
    cities = ['москва', 'санкт-петербург', 'новосибирск', 'екатеринбург', 'казань', 
              'нижний новгород', 'челябинск', 'самара', 'омск', 'ростов', 'уфа', 
              'красноярск', 'пермь', 'волгоград', 'воронеж']
    
    message_lower = message.lower()
    for city in cities:
        if city in message_lower:
            return city.capitalize()
    
    # Если город не найден, пробуем извлечь любое слово с большой буквы
    words = re.findall(r'\b[А-Я][а-я]+\b', message)
    return words[0] if words else "Москва"  # По умолчанию Москва

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
    # ... (предыдущая реализация остается)

def detect_communication_style(message: str) -> str:
    """Определяет стиль общения по сообщению"""
    # ... (предыдущая реализация остается)

def detect_function_request(message: str) -> str:
    """Определяет, запрашивает ли пользователь дополнительную функцию"""
    lower_message = message.lower()
    
    for func, triggers in FUNCTION_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return func
    
    return None

@lru_cache(maxsize=100)
def generate_prompt_template(style: str = 'neutral') -> str:
    """Генерирует промпт для выбранного стиля"""
    return COMMUNICATION_STYLES[style]['prompt']

async def call_yandex_gpt_optimized(user_message: str, style: str = 'neutral') -> str:
    """Оптимизированный вызов API с учетом стиля"""
    # ... (предыдущая реализация остается)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений с дополнительными функциями"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_message = update.message.text
    
    # Проверяем запросы на дополнительные функции
    requested_function = detect_function_request(user_message)
    
    if requested_function:
        await update.message.chat.send_action(action="typing")
        
        try:
            if requested_function == 'weather':
                city = extract_city_from_message(user_message)
                weather_info = await get_weather(city)
                await update.message.reply_text(weather_info)
                
            elif requested_function == 'traffic':
                city = extract_city_from_message(user_message)
                traffic_info = await get_traffic(city)
                await update.message.reply_text(traffic_info)
                
            elif requested_function == 'news':
                news_info = await get_news()
                await update.message.reply_text(news_info)
                
            return
            
        except Exception as e:
            logger.error(f"Function error: {e}")
            # Продолжаем к обычному ответу
    
    # Обычная обработка сообщений
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    style = detect_communication_style(user_message)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        ai_response = await call_yandex_gpt_optimized(user_message, style)
        
        # Добавляем имя в ответ
        final_response = f"{transformed_name}, {ai_response}"
        await update.message.reply_text(final_response)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Я Юля, кстати 😉")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    help_text = f"""
👋 Привет! Я {BOT_PROFILE['name']}, {BOT_PROFILE['age']}-летний ассистент.

✨ Что я умею:
• Общаться на разные темы
• Рассказывать о погоде (напиши 'погода в Москве')
• Сообщать о пробках ('пробки в Питере')
• Показывать новости ('новости')

💬 Мой характер: {BOT_PROFILE['personality']}
🎭 Могу быть: дружелюбной, саркастичной, строгой или игривой

Просто напиши мне что-нибудь! 💕
"""
    await update.message.reply_text(help_text)

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/help$'),
            help_command
        ))
        
        print(f"🤖 {BOT_PROFILE['name']} запущена!")
        print(f"📍 Возраст: {BOT_PROFILE['age']} лет")
        print(f"📍 Характер: {BOT_PROFILE['personality']}")
        print("📍 Функции: погода, пробки, новости")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
