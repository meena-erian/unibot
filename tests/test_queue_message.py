from django.test import TestCase
from django.utils import timezone

from unicom.models import Account, Channel, Chat, Message, Request
from unicom.services.message_batches import save_incoming_message_batch
from unibot.models import Bot


class QueueMessageTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(name="Example", platform="WebChat", config={})
        self.account = Account.objects.create(id="example", channel=self.channel, platform="WebChat")
        self.chat = Chat.objects.create(id="example", channel=self.channel, platform="WebChat")
        self.bot = Bot.objects.create(name="Example", category="Example", code="")

    def part(self, identifier):
        return Message(id=identifier, channel=self.channel, platform="WebChat", sender=self.account, chat=self.chat, is_outgoing=False, sender_name="Example", text=identifier, timestamp=timezone.now())

    def test_final_message_is_routed_once_without_provider_execution(self):
        first, final = save_incoming_message_batch([self.part("first"), self.part("final")])
        queued = self.bot.queue_message(final, display_text="Compare", metadata={"purpose": "example"})
        self.assertEqual(queued.status, "QUEUED")
        self.assertEqual(queued.category, self.bot.request_category)
        self.assertEqual(queued.message.reply_to_message, first)
        self.assertEqual(queued.display_text, "Compare")
        self.assertEqual(queued.metadata, {"purpose": "example"})
        with self.assertRaises(ValueError):
            self.bot.queue_message(final)
        self.assertEqual(Request.objects.count(), 1)

    def test_unsaved_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bot.queue_message(self.part("unsaved"))
