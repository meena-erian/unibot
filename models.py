from django.db import models
import os
from django.conf import settings
from unicom.models import RequestCategory, Message
from unibot.services.llm_handler import run_llm_handler
from typing import Callable, Dict, List, Optional, Type
import types
import traceback
from openai import OpenAI
import reversion
from django.utils import timezone
from datetime import timedelta

# Create your models here.

@reversion.register()
class Tool(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Store the implementation code, which must define a `tool_definition` dict
    code = models.TextField(
        blank=True,
        help_text="Python implementation including a top-level `tool_definition` dict"
    )

    def __str__(self):
        return self.name

    @property
    def info(self) -> str:
        """Returns structured information about the tool"""
        return (
            f"Tool ID: {self.id}\n"
            f"Name: {self.name}\n"
            f"Code: \n{self.code}\n"
        )

    def get_definition(self):
        """
        Execute the tool's code in isolation and return its `tool_definition` dict.
        """
        module = types.ModuleType('tool_module')
        exec(self.code, module.__dict__)
        return getattr(module, 'tool_definition', None)

    @staticmethod
    def get_default_code():
        template_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'default_tool.py')
        with open(template_path, 'r') as f:
            return f.read()

    @classmethod
    def get_template_readme(cls) -> str:
        """Returns the contents of TOOL_TEMPLATES_README.md"""
        readme_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'TOOL_TEMPLATES_README.md')
        try:
            with open(readme_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Tool template documentation not found."

@reversion.register()
class Bot(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    code = models.TextField()
    request_category = models.OneToOneField(RequestCategory, on_delete=models.CASCADE, null=True, blank=True)
    # New many-to-many relationship to attach tools
    tools = models.ManyToManyField(Tool, blank=True, related_name='bots')

    def __str__(self):
        return self.name

    @property
    def info(self) -> str:
        """Returns structured information about the bot"""
        # Get tools info
        tools_info = ", ".join([f"{tool.name} (ID: {tool.id})" for tool in self.tools.all()])
        
        # Get recent error if any
        recent_error = ""
        if self.request_category:
            # Assuming Request model has status, created_at, and error fields
            twelve_hours_ago = timezone.now() - timedelta(hours=24)
            recent_failed_request = (
                self.request_category.request_set
                .filter(status='FAILED', created_at__gte=twelve_hours_ago)
                .order_by('-created_at')
                .first()
            )
            if recent_failed_request:
                recent_error = f"\nLast Recent Error: {recent_failed_request.error}"

        return (
            f"Bot ID: {self.id}\n"
            f"Name: {self.name}\n"
            + (f"Tools: {tools_info}\n" if tools_info else "")
            + f"Code: \n{self.code}\n"
            + (f"Recent Error: {recent_error}\n" if recent_error else "")
        )

    @classmethod
    def get_template_readme(cls) -> str:
        """Returns the contents of BOT_TEMPLATES_README.md"""
        readme_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'BOT_TEMPLATES_README.md')
        try:
            with open(readme_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Bot template documentation not found."

    @staticmethod
    def get_default_code():
        template_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'default_bot.py')
        with open(template_path, 'r') as f:
            return f.read()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.request_category:
            rc = RequestCategory.objects.create(
                name=self.category,
                sequence=1000 + self.id
            )
            self.request_category = rc
            super().save(update_fields=['request_category'])

    def delete(self, *args, **kwargs):
        rc = self.request_category
        super().delete(*args, **kwargs)
        if rc:
            rc.delete()

    def reply_using_llm(
        self,
        message: Message,
        tools_list: List[Tool],
        model_audio: str = "gpt-4o-audio-preview",
        model_default: str = "o4-mini-2025-04-16",
        system_instruction: Optional[str] = None,
        depth: int = 10,
        mode: str = "thread",
        max_function_calls: int = 3,
        openai_client: OpenAI = None,
    ):
        if openai_client is None:
            openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return run_llm_handler(
            self,
            message,
            tools_list,
            model_audio=model_audio,
            model_default=model_default,
            system_instruction=system_instruction,
            max_function_calls=max_function_calls,
            as_llm_chat_params={
                "depth": depth,
                "mode": mode,
            },
            openai_client=openai_client,
        )

    def process_request(self, req):
        """
        Process a single Request object using this bot's code, updating status and error fields as needed.
        Passes the bot instance and its associated tools to the handler.
        """
        bot_code = self.code or Bot.get_default_code()
        module = types.ModuleType('bot_code')
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        module.__dict__["openai_client"] = openai_client
        tools_list = list(self.tools.all())
        try:
            exec(bot_code, module.__dict__)
            handler = getattr(module, 'handle_incoming_message', None)
            if not handler:
                # Use default handler from default_bot.py
                default_code = Bot.get_default_code()
                exec(default_code, module.__dict__)
                handler = getattr(module, 'handle_incoming_message', None)
            if not handler:
                req.status = 'FAILED'
                req.error = f'No handle_incoming_message function defined for bot {self.id}'
                req.save(update_fields=['status', 'error'])
                return False
            # Pass message, bot instance, and tools list
            handler(req.message, self, tools_list)
            req.status = 'COMPLETED'
            req.save(update_fields=['status'])
            return True
        except Exception as e:
            req.status = 'FAILED'
            req.error = traceback.format_exc()
            req.save(update_fields=['status', 'error'])
            return False
