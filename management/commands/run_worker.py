from django.core.management.base import BaseCommand
from django.db import transaction
from unicom.models.request import Request
from unibot.models import Bot
import importlib.util
import os
import time
from django.conf import settings
from openai import OpenAI
import traceback

class Command(BaseCommand):
    help = 'Run the bot worker to process requests.'

    def add_arguments(self, parser):
        parser.add_argument('--bot-id', type=int, help='ID of the bot to use (optional)')
        parser.add_argument('--status', type=str, help='Status of requests to process (default: QUEUED)', default='QUEUED')
        parser.add_argument('--limit', type=int, help='Limit number of requests to process per loop')
        parser.add_argument(
            '--sleep', type=float,
            help='Seconds to wait when the queue is empty (default: 0.1)',
            default=0.1,
        )

    def handle(self, *args, **options):
        bot_id = options.get('bot_id')
        status = options.get('status', 'QUEUED')
        limit = options.get('limit')
        sleep_time = options.get('sleep', 2)

        self.stdout.write(self.style.SUCCESS('Starting worker. Press Ctrl+C to stop.'))
        next_expiry_check = 0
        try:
            while True:
                if time.monotonic() >= next_expiry_check:
                    from unicom.services.interactions import expire_interactions
                    expire_interactions()
                    next_expiry_check = time.monotonic() + 30
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
                processed = 0
                while limit is None or processed < limit:
                    # Claim and commit one request before doing provider or tool work.
                    # This prevents long external calls from holding row locks and makes
                    # incremental message updates visible to web processes immediately.
                    with transaction.atomic():
                        req = (
                            Request.objects.select_for_update(skip_locked=True)
                            .filter(category_id__in=categories, status=status)
                            .order_by('created_at')
                            .first()
                        )
                        if req is None:
                            break
                        req.status = 'PROCESSING'
                        req.error = None
                        req.save(update_fields=['status', 'error'])

                    bot = bot_map.get(req.category_id)
                    if not bot:
                        req.status = 'FAILED'
                        req.error = f'No bot found for category {req.category_id}'
                        req.save(update_fields=['status', 'error'])
                        self.stderr.write(self.style.ERROR(req.error))
                        continue
                    result = bot.process_request(req)
                    if result:
                        processed += 1
                        self.stdout.write(self.style.SUCCESS(f'Processed request {req.id}'))
                    else:
                        self.stderr.write(self.style.ERROR(f'Failed to process request {req.id}: {getattr(req, "error", "Unknown error")}'))
                if processed == 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Worker stopped by user.'))
