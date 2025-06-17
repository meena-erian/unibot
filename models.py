from django.db import models
import os
from django.conf import settings
from unicom.models.request_category import RequestCategory
import types
import traceback
from openai import OpenAI

# Create your models here.

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

    def get_definition(self):
        """
        Execute the tool's code in isolation and return its `tool_definition` dict.
        """
        module = types.ModuleType('tool_module')
        exec(self.code, module.__dict__)
        return getattr(module, 'tool_definition', None)

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

    def process_request(self, req):
        """
        Process a single Request object using this bot's code, updating status and error fields as needed.
        Passes the bot instance and its associated tools to the handler.
        """
        bot_code = self.code or Bot.get_default_code()
        module = types.ModuleType('bot_code')
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        module.__dict__["openai_client"] = openai_client
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

        # Gather tools assigned to this bot
        tools_list = list(self.tools.all())

        try:
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
