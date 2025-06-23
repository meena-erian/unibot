## Basic Bot Template

The simplest bot implementation looks like this:

```python
def handle_incoming_message(message, bot, tools_list):
    return bot.reply_using_llm(
        message, tools_list,
        system_instruction="You are a helpful AI assistant"
    )
```

## Message Handling Examples

### Different Response Types
```python
# Text messages
message.reply_with({"text": "Hello!"})

# HTML responses (only supported if message.platform == 'Email')
message.reply_with({"html": "<p>Formatted <b>response</b></p>"})

# Audio processing
if message.media_type == 'audio':
    return message.reply_using_llm(model="gpt-4-audio-preview")
```

### Advanced Features
```python
# Using tools with conversation context
response = message.reply_using_llm(
    tools_list=tools_list,
    mode="thread"  # Maintains conversation history
)

# File handling
message.reply_with({
    "text": "Here's your file",
    "files": ["path/to/file.pdf"]
})
