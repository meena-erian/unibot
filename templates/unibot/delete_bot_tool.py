from django.core.exceptions import ObjectDoesNotExist
from unibot.models import Bot
import reversion

def delete_bot(bot_id: int) -> dict:
    """Deletes a bot"""
    try:
        with reversion.create_revision():
            bot = Bot.objects.get(id=bot_id)
            reversion.set_comment("Final revision before deletion via delete_bot tool")
            bot.delete()
        return {"success": True}
    except ObjectDoesNotExist:
        return {"success": False, "error": f"Bot with ID {bot_id} not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

tool_definition = {
    "name": "delete_bot",
    "description": "Delete a bot",
    "parameters": {
        "bot_id": {
            "type": "integer",
            "description": "ID of the bot to delete"
        }
    },
    "run": delete_bot
} 