from telegram.ext import Updater, CommandHandler
import os

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Let's build a telegram bot that help people learn English faster")

def main():
    # Use environment variable for token for better security; replace with your token for testing
    token = os.environ.get('BOT_TOKEN', '6774835592:AAFI-egcgqCttSq5V9W8QHxQAgbf4LY_cMU')

    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher

    start_handler = CommandHandler('start', start)
    dispatcher.add_handler(start_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
