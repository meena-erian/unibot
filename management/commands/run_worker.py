from django.core.management.base import BaseCommand
from django.db import transaction
from unicom.models.request import Request
from unibot.models import Bot
import importlib.util
import os
import time

class Command(BaseCommand):
    help = 'Run the bot worker to process requests.'

    def add_arguments(self, parser):
        parser.add_argument('--bot-id', type=int, help='ID of the bot to use (optional)')
        parser.add_argument('--status', type=str, help='Status of requests to process (default: QUEUED)', default='QUEUED')
        parser.add_argument('--limit', type=int, help='Limit number of requests to process per loop')
        parser.add_argument('--sleep', type=int, help='Seconds to sleep between loops', default=2)

    def handle(self, *args, **options):
        bot_id = options.get('bot_id')
        status = options.get('status', 'QUEUED')
        limit = options.get('limit')
        sleep_time = options.get('sleep', 2)

        self.stdout.write(self.style.SUCCESS('Starting worker. Press Ctrl+C to stop.'))
        try:
            while True:
                if bot_id:
                    bots = Bot.objects.filter(id=bot_id)
                else:
                    bots = Bot.objects.all()
                bot_map = {bot.request_category_id: bot for bot in bots if bot.request_category_id}
                if not bot_map:
                    self.stdout.write(self.style.WARNING('No bots with request categories found.'))
                    time.sleep(sleep_time)
                    continue
                categories = list(bot_map.keys())
                # Get requests for these categories
                qs = Request.objects.select_for_update(skip_locked=True).filter(category_id__in=categories, status=status)
                if limit:
                    qs = qs[:limit]
                processed = 0
                with transaction.atomic():
                    for req in qs:
                        bot = bot_map.get(req.category_id)
                        if not bot:
                            self.stderr.write(self.style.ERROR(f'No bot found for category {req.category_id}'))
                            continue
                        # Load bot code
                        import types
                        bot_code = bot.code or Bot.get_default_code()
                        module = types.ModuleType('bot_code')
                        exec(bot_code, module.__dict__)
                        handler = getattr(module, 'handle_incoming_message', None)
                        if not handler:
                            # Use default handler from default_bot.py
                            default_code = Bot.get_default_code()
                            exec(default_code, module.__dict__)
                            handler = getattr(module, 'handle_incoming_message', None)
                        if not handler:
                            self.stderr.write(self.style.ERROR(f'No handle_incoming_message function defined for bot {bot.id}'))
                            continue
                        try:
                            handler(req.message, bot)
                            req.status = 'COMPLETED'
                            req.save(update_fields=['status'])
                            processed += 1
                            self.stdout.write(self.style.SUCCESS(f'Processed request {req.id}'))
                        except Exception as e:
                            req.status = 'FAILED'
                            req.error = str(e)
                            req.save(update_fields=['status', 'error'])
                            self.stderr.write(self.style.ERROR(f'Failed to process request {req.id}: {e}'))
                if processed == 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Worker stopped by user.')) 