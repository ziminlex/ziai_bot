import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import requests
import json

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# URL API DeepSeek
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие сообщения и отправляет ответ от AI."""
    user_message = update.message.text
    
    # Показываем статус "печатает..."
    await update.message.chat.send_action(action="typing")
    
    try:
        # Подготавливаем запрос к DeepSeek API
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": user_message}],
            "stream": False
        }
        
        # Отправляем запрос
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        response.raise_for_status()  # Проверяем на ошибки HTTP
        
        # Парсим ответ
        result = response.json()
        ai_response = result['choices'][0]['message']['content']
        
        # Отправляем ответ пользователю
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к DeepSeek: {e}")
        if 'response' in locals():
            logger.error(f"Response status: {response.status_code}")
            logger.error(f"Response text: {response.text}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте еще раз.")

def main():
    """Запускает бота."""
    # Создаем приложение и передаем ему токен
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчик для текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    print("Бот запущен!")

if __name__ == "__main__":
    main()


