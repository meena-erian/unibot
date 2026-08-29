from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from unibot.services.llm_handler import run_llm_handler


class BotResponsesApiTests(SimpleTestCase):
    def setUp(self):
        self.message = Mock()
        self.message.as_llm_chat.return_value = [{"role": "user", "content": "Hello"}]
        self.message.reply_with.return_value = "saved-reply"
        self.client = Mock()

    def test_responses_mode_persists_normalized_text(self):
        self.client.responses.create.return_value = SimpleNamespace(output_text="Hi")

        result = run_llm_handler(
            bot=Mock(),
            message=self.message,
            tools_list=[],
            model_default="test-model",
            openai_client=self.client,
            api_mode="responses",
        )

        self.assertEqual(result, "saved-reply")
        self.client.responses.create.assert_called_once_with(
            model="test-model",
            input=[{"role": "user", "content": "Hello"}],
        )
        self.client.chat.completions.create.assert_not_called()
        self.message.reply_with.assert_called_once_with({"type": "text", "text": "Hi"})

    def test_default_mode_remains_chat_completions(self):
        self.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hi", tool_calls=None))]
        )

        run_llm_handler(
            bot=Mock(),
            message=self.message,
            tools_list=[],
            model_default="test-model",
            openai_client=self.client,
        )

        self.client.chat.completions.create.assert_called_once()
        self.client.responses.create.assert_not_called()

    def test_streaming_emits_normalized_events_and_reuses_sink_message(self):
        streamed_reply = object()
        sink = Mock(return_value=streamed_reply)
        self.client.responses.create.return_value = iter([
            SimpleNamespace(
                type="response.created",
                response=SimpleNamespace(id="resp_123"),
            ),
            SimpleNamespace(type="response.output_text.delta", delta="Hel"),
            SimpleNamespace(type="response.output_text.delta", delta="lo"),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(id="resp_123"),
            ),
        ])

        result = run_llm_handler(
            bot=Mock(), message=self.message, tools_list=[],
            model_default="test-model", openai_client=self.client,
            api_mode="responses", stream=True, event_sink=sink,
        )

        self.assertIs(result, streamed_reply)
        self.client.responses.create.assert_called_once_with(
            model="test-model",
            input=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
        self.assertEqual(sink.call_args_list[0].args[0], {"type": "started"})
        self.assertEqual(sink.call_args_list[1].args[0], {"type": "text.delta", "delta": "Hel"})
        self.assertEqual(sink.call_args_list[2].args[0], {"type": "text.delta", "delta": "lo"})
        self.assertEqual(sink.call_args_list[3].args[0], {
            "type": "finished", "text": "Hello", "response_id": "resp_123",
        })
        self.message.reply_with.assert_not_called()

    def test_streaming_failure_is_reported_and_reraised(self):
        sink = Mock()
        self.client.responses.create.side_effect = RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            run_llm_handler(
                bot=Mock(), message=self.message, tools_list=[],
                model_default="test-model", openai_client=self.client,
                api_mode="responses", stream=True, event_sink=sink,
            )

        self.assertEqual(sink.call_args_list[0].args[0], {"type": "started"})
        self.assertEqual(sink.call_args_list[-1].args[0]["type"], "failed")
        self.assertIn("provider unavailable", sink.call_args_list[-1].args[0]["error"])
