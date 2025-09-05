import compatibility
import os
import logging
import requests
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")  # Новый ключ для Yandex GPT
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")  # ID вашего каталога в Yandex Cloud

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие сообщения и отправляет ответ от AI."""
    user_message = update.message.text
    
    # Показываем статус "печатает..."
    await update.message.chat.send_action(action="typing")
    
    try:
        # Подготавливаем запрос к Yandex GPT API
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": 2000
            },
            "messages": [
                {
                    "role": "system", 
                    "text": "Ты полезный AI-ассистент в Telegram. Отвечай кратко и по делу."
                },
                {
                    "role": "user",
                    "text": user_message
                }
            ]
        }
        
        # Отправляем запрос
        response = requests.post(YANDEX_API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        # Парсим ответ
        result = response.json()
        ai_response = result['result']['alternatives'][0]['message']['text']
        
        # Отправляем ответ пользователю
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к Yandex GPT: {e}")
        if 'response' in locals():
            logger.error(f"Response status: {response.status_code}")
            logger.error(f"Response text: {response.text}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте еще раз.")

def main():
    """Запускает бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    print("Бот запущен!")

if __name__ == "__main__":
    main()




