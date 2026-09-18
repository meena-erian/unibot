from types import SimpleNamespace
from contextlib import nullcontext
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from unicom.models import Account, Channel, Chat, Message, Request

from unibot.services.llm_handler import run_llm_handler


class LlmHandlerOrderingTests(SimpleTestCase):
    @patch('unibot.services.llm_handler.transaction.atomic', side_effect=lambda: nullcontext())
    @patch("unibot.services.llm_handler._request_was_superseded", return_value=False)
    @patch("unicom.services.llm.responses.create_response")
    @patch("unibot.services.llm_handler.build_openai_tools")
    def test_text_before_tool_call_is_persisted_before_tool_activity(
        self, build_tools, create, _superseded, _atomic,
    ):
        events = []
        message = SimpleNamespace(
            media_type="text",
            as_llm_chat=lambda **_kwargs: [{"role": "user", "content": "help"}],
            reply_with=lambda reply: events.append(("reply", reply.copy())) or SimpleNamespace(pk='preamble-1'),
        )
        stored_call = SimpleNamespace(
            raw={'tool_call': {'id': 'call-1'}},
            save=lambda **kwargs: events.append(('link', kwargs)),
        )
        tool_call = SimpleNamespace(
            mark_active=lambda: events.append(("active", None)),
            tool_call_message=stored_call,
        )
        request = SimpleNamespace(
            submit_tool_calls=lambda calls: events.append(("submit", calls)) or [tool_call],
        )
        create.return_value = SimpleNamespace(
            text="First, choose the scope.", content=[], response_id="response-1",
            tool_calls=[SimpleNamespace(call_id="call-1", name="ask", arguments={})],
        )
        build_tools.return_value = (
            [{"type": "function", "function": {"name": "ask"}}],
            {"ask": lambda: None},
            {"ask": []},
        )

        run_llm_handler(
            bot=SimpleNamespace(), message=message, tools_list=[], request=request,
            api_mode="responses", openai_client=SimpleNamespace(),
        )

        self.assertEqual([event[0] for event in events[:2]], ["reply", "submit"])
        self.assertEqual(events[0][1]["text"], "First, choose the scope.")
        self.assertEqual(stored_call.raw, {
            'tool_call': {'id': 'call-1'},
            'assistant_preamble_message_id': 'preamble-1',
        })
        self.assertEqual([event[0] for event in events], ['reply', 'submit', 'link', 'active'])
        self.assertEqual(
            events[0][1]["_message_raw"],
            {"assistant_phase": "tool_preamble"},
        )


class PersistedHandlerHistoryTests(TestCase):
    @patch.object(Request, 'categorize')
    @patch.object(Request, 'identify_member')
    @patch('unicom.services.llm.responses.create_response')
    @patch('unibot.services.llm_handler.build_openai_tools')
    def test_provider_text_links_to_every_call_and_survives_continuation(
        self, build_tools, create, _identify, _categorize,
    ):
        channel = Channel.objects.create(name='preamble-handler', platform='WebChat', config={})
        account = Account.objects.create(id='preamble-user', channel=channel, platform='WebChat', raw={})
        chat = Chat.objects.create(id='preamble-chat', channel=channel, platform='WebChat')
        message = Message.objects.create(
            id='preamble-input', channel=channel, platform='WebChat', sender=account,
            chat=chat, is_outgoing=False, sender_name='User', text='Run both',
            timestamp=timezone.now(), raw={'skip_request_creation': True},
        )
        request = Request.objects.create(message=message, account=account, channel=channel)
        create.return_value = SimpleNamespace(
            text='I will check both.', content=[], response_id='provider-output',
            tool_calls=[
                SimpleNamespace(call_id='handler-first', name='ask', arguments={}),
                SimpleNamespace(call_id='handler-second', name='ask', arguments={}),
            ],
        )
        build_tools.return_value = (
            [{'type': 'function', 'function': {'name': 'ask'}}],
            {'ask': lambda: None}, {'ask': []},
        )
        with self.captureOnCommitCallbacks(execute=True):
            run_llm_handler(
                bot=SimpleNamespace(), message=message, tools_list=[], request=request,
                api_mode='responses', openai_client=SimpleNamespace(),
            )
        preamble = chat.messages.get(raw__assistant_phase='tool_preamble')
        calls = list(request.tool_calls.order_by('created_at'))
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call.tool_call_message.raw['assistant_preamble_message_id'], preamble.pk)
        calls[1].respond({'result': 'second'})
        _response, continuation = calls[0].respond({'result': 'first'})
        history = continuation.message.as_llm_chat(mode='thread', multimodal=False)
        self.assertEqual([item['role'] for item in history], [
            'user', 'assistant', 'assistant', 'tool', 'assistant', 'tool',
        ])
        self.assertEqual(history[1]['content'], 'I will check both.')
        self.assertEqual(history[2]['tool_calls'][0]['id'], 'handler-first')
        self.assertEqual(history[4]['tool_calls'][0]['id'], 'handler-second')
