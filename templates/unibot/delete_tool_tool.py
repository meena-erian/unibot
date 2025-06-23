from django.core.exceptions import ObjectDoesNotExist
from unibot.models import Tool
import reversion

def delete_tool(tool_id: int) -> dict:
    """Deletes a tool"""
    try:
        with reversion.create_revision():
            tool = Tool.objects.get(id=tool_id)
            reversion.set_comment("Final revision before deletion via delete_tool tool")
            tool.delete()
        return {"success": True}
    except ObjectDoesNotExist:
        return {"success": False, "error": f"Tool with ID {tool_id} not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

tool_definition = {
    "name": "delete_tool",
    "description": "Delete a tool",
    "parameters": {
        "tool_id": {
            "type": "integer",
            "description": "ID of the tool to delete"
        }
    },
    "run": delete_tool
} 