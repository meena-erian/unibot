def handle_incoming_message(message, bot, tools_list):
    return bot.reply_using_llm(
        message, 
        tools_list,
        system_instruction="You are Insightifyr AI, a powerful AI capable of browsing the web"
    )