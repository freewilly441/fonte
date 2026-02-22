import unittest

import llm


class _FakeLLM:
    def __init__(self):
        self.last_prompt = ""
        self.last_stop = None

    def __call__(self, prompt, max_tokens=128, temperature=0.3, top_p=0.9, top_k=40, stop=None):
        self.last_prompt = prompt
        self.last_stop = stop
        return {"choices": [{"text": "- point one\n- point two"}]}


class LlmLocalTests(unittest.TestCase):
    def test_generate_answer_with_mock_model(self):
        fake = _FakeLLM()
        out = llm.generate_answer(fake, "How does caching work?", [], max_tokens=96)
        self.assertIn("point one", out)
        self.assertIn("You are a helpful assistant.", fake.last_prompt)
        self.assertIn("Do not repeat the question.", fake.last_prompt)
        self.assertIn("Q: What is the number after 9?", fake.last_prompt)
        self.assertIn("Q: How does caching work?", fake.last_prompt)
        self.assertIn("\nA:", fake.last_prompt)
        self.assertEqual(fake.last_stop, llm.STOP_SEQUENCES)

    def test_build_prompt_with_context_uses_grounded_template(self):
        prompt = llm.build_prompt("What is Foo?", [(1, "Doc", "src", "Foo is a bar.")])
        self.assertIn("Do not repeat the question.", prompt)
        self.assertIn("Context:", prompt)
        self.assertIn("[1] Doc (src)", prompt)
        self.assertIn("Q: What is Foo?", prompt)
        self.assertIn("A:", prompt)

    def test_generate_answer_removes_leading_query_echo(self):
        class _EchoLLM:
            def __call__(self, prompt, **_kwargs):
                return {"choices": [{"text": "How does caching work? Caching stores computed results."}]}

        out = llm.generate_answer(_EchoLLM(), "How does caching work?", [], max_tokens=64)
        self.assertEqual(out, "Caching stores computed results.")


if __name__ == "__main__":
    unittest.main()
