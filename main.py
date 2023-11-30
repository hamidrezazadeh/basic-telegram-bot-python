import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import openai

def handle_message(update, context):
    user_message = update.message.text

    # Fetching the API key from environment variables
    openai_api_key = os.environ.get('OPENAI_API_KEY')

    openai.api_key = openai_api_key

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # Adjust the model as per your access
        messages=[{"role": "user", "content": user_message}]
    )

    # Send the response back to the user
    context.bot.send_message(chat_id=update.effective_chat.id, text=response.choices[0].message['content'])

def main():
    token = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
    
    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher

    message_handler = MessageHandler(Filters.text & (~Filters.command), handle_message)
    dispatcher.add_handler(message_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
