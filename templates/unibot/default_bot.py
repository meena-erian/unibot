# Default bot handler

def handle_incoming_message(message, bot):
    """
    Handles an incoming message for the bot.
    Uses ChatGPT if openai_client is available, otherwise replies with a default message.
    """
    global openai_client
    if openai_client and hasattr(openai_client, 'chat'):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": message.text}]
            )
            message.reply_with({
                "text": response.choices[0].message.content
            })
            return
        except Exception as e:
            message.reply_with({
                "text": f"Error using OpenAI: {e}"
            })
            return
    message.reply_with({
        "text": f"Message handled by {bot.name}. If you are seeing this, you probably didn't yet define how this bot should respond"
    })
