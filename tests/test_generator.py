import io
import json
import unittest
from unittest.mock import patch
from app.rag import generator


class FallbackTests(unittest.TestCase):
    def test_nvidia_fallback_returns_answer_with_bounded_non_thinking_output(self):
        response={"choices":[{"message":{"content":"A grounded answer"}}],"usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}}
        with (patch.object(generator,"GEMINI_API_KEY",""),patch.object(generator,"GROQ_API_KEY",""),
              patch.object(generator,"NVIDIA_API_KEY","test-value"),
              patch.object(generator,"NVIDIA_MODEL","nvidia/nemotron-3.5-lightning-30b-a3b"),
              patch("urllib.request.urlopen",return_value=io.BytesIO(json.dumps(response).encode())) as send):
            answer,trace=generator.generate_with_trace("Explain",[])
        self.assertEqual(answer,"A grounded answer")
        self.assertEqual(trace["provider"],"nvidia")
        self.assertEqual(trace["images_seen"],0)
        request=send.call_args.args[0]
        payload=json.loads(request.data)
        self.assertEqual(payload["max_tokens"],4096)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(request.get_header("User-agent"),"Prism/1.0")
