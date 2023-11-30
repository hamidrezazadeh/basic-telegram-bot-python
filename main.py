from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import openai
import os

def handle_message(update, context):
    user_message = update.message.text

    # OpenAI API call
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # or another model you have access to
        messages=[{"role": "user", "content": user_message}]
    )

    # Send the response back to the user
    context.bot.send_message(chat_id=update.effective_chat.id, text=response.choices[0].message['content'])

def main():
    # Use environment variable for token
    token = os.environ.get('BOT_TOKEN', '6774835592:AAFI-egcgqCttSq5V9W8QHxQAgbf4LY_cMU')
    openai.api_key = os.environ.get('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')  # Set your OpenAI API key

    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher

    # Message handler
    message_handler = MessageHandler(Filters.text & (~Filters.command), handle_message)
    dispatcher.add_handler(message_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
