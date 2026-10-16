"""Bind definition-local interaction classes to stable persisted identifiers."""
import re
from django.contrib.staticfiles.storage import staticfiles_storage
from unicom.interactions import MessageWithButtons


def bind_interactions(tool_name, definition):
    for name, cls in (definition.get('interactions') or {}).items():
        if not re.fullmatch(r'[A-Za-z0-9_]+', name) or not issubclass(cls, MessageWithButtons):
            raise ValueError('Invalid interaction declaration')
        cls.handler_key = f'unibot:{tool_name}:{name}'
        component = getattr(cls, 'web_component', None)
        if isinstance(component, str):
            expected = f'{tool_name}.presentation.js'
            if component != expected:
                raise ValueError(f'Web component must be named {expected}')
            cls.web_component = {'module': staticfiles_storage.url(f'unibot/definitions/{component}')}
    return definition


def resolve_interaction(identifier):
    from unibot.models import Tool
    tool_name, name = identifier.split(':', 1)
    definition = Tool.objects.get(name=tool_name).get_definition()
    return definition['interactions'][name]


def handle_interaction_result(result, tool_call):
    """Shared execution hook for UniBot and custom provider adapters."""
    if not isinstance(result, MessageWithButtons):
        return False
    from unicom.services.interactions import start_interaction
    start_interaction(result, tool_call)
    return True
