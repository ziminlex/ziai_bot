import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from deepseek import DeepSeekAPI

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ваши ключи (будут заданы через переменные окружения на Render.com)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Сюда автоматически подставится ваш токен
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")      # Сюда автоматически подставится ваш ключ DeepSeek

# Инициализируем клиента DeepSeek
client = DeepSeek(api_key=DEEPSEEK_API_KEY)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие сообщения и отправляет ответ от AI."""
    user_message = update.message.text
    
    # Показываем статус "печатает..."
    await update.message.chat.send_action(action="typing")
    
    try:
        # Отправляем запрос в DeepSeek
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": user_message}],
            stream=False
        )
        
        # Извлекаем ответ
        ai_response = response.choices[0].message.content
        
        # Отправляем ответ пользователю
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к DeepSeek: {e}")
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
