from unibot.models import Tool
import reversion

def create_tool(name: str, code: str) -> dict:
    """Creates a new tool"""
    try:
        with reversion.create_revision():
            tool = Tool.objects.create(
                name=name,
                description="",  # Empty as per requirements
                code=code
            )
            reversion.set_comment("Initial revision via create_tool tool")
        return {"success": True, "tool_id": tool.id}
    except Exception as e:
        return {"success": False, "error": str(e)}

tool_definition = {
    "name": "create_tool",
    "description": "Create a new tool",
    "parameters": {
        "name": {
            "type": "string",
            "description": "Name of the tool"
        },
        "code": {
            "type": "string",
            "description": "Python code for the tool"
        }
    },
    "run": create_tool
} 