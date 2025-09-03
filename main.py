import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from deepseek import DeepSeekAPI  # Правильный импорт

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Правильная инициализация клиента
client = DeepSeekAPI(api_key=DEEPSEEK_API_KEY)  # Используем DeepSeekAPI вместо DeepSeek

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие сообщения и отправляет ответ от AI."""
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": user_message}],
            stream=False
        )
        
        ai_response = response.choices[0].message.content
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к DeepSeek: {e}")
        await update.message.reply_text("Извините, произошла ошибка. Попробуйте еще раз.")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    print("Бот запущен!")

if __name__ == "__main__":
    main()

