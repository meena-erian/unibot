# Default bot handler

def handle_incoming_message(message, bot):
    """
    Handles an incoming message for the bot.
    :param message: Message object (from unicom.models.message)
    :param bot: Bot object (from unibot.models)
    """
    message.reply_with({
        "text": f"Message handled by {bot.name}. If you are seeing this, you probably didn't yet define how this bot should respond"
    })
