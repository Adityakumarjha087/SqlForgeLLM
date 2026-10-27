"""Model backends for serving: one protocol, four implementations.

- vllm:          GPU deployments; continuous batching, by far the best throughput
- transformers:  works anywhere torch does (CPU/MPS/CUDA); simplest, slowest
- ollama:        local CPU via a merged + GGUF-quantized model (see docs/decisions.md)
- mock:          deterministic canned output for tests and frontend development
"""

from dataclasses import dataclass
from typing import Protocol

from sqlforge.data.prompting import build_messages, extract_sql


@dataclass
class Generation:
    sql: str
    completion_tokens: int | None = None


class ModelBackend(Protocol):
    def generate(self, schema: str, question: str) -> Generation: ...


class MockBackend:
    """Returns a fixed, parseable query; tests and `web/` dev run against this."""

    def generate(self, schema: str, question: str) -> Generation:
        first_table = "sqlite_master"
        for line in schema.splitlines():
            if "(" in line:
                name = line.split("(")[0].replace("CREATE TABLE", "").strip().strip('"')
                if name:
                    first_table = name
                    break
        return Generation(sql=f'SELECT count(*) FROM "{first_table}"', completion_tokens=7)


class TransformersBackend:
    def __init__(self, model_id: str, adapter: str | None, max_new_tokens: int):
        from sqlforge.eval.generate import load_model

        self.lm = load_model(model_id, adapter_path=adapter or None)
        self.max_new_tokens = max_new_tokens

    def generate(self, schema: str, question: str) -> Generation:
        import torch

        tokenizer = self.lm.tokenizer
        prompt = tokenizer.apply_chat_template(
            build_messages(schema, question), tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(self.lm.device)
        with torch.no_grad():
            output = self.lm.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        new_tokens = output[0, inputs["input_ids"].shape[1] :]
        completion = tokenizer.decode(new_tokens, skip_special_tokens=True)
        return Generation(sql=extract_sql(completion), completion_tokens=len(new_tokens))


class VLLMBackend:
    def __init__(self, model_id: str, adapter: str | None, max_new_tokens: int):
        from vllm import LLM, SamplingParams
        from vllm.lora.request import LoRARequest

        self.llm = LLM(model=model_id, enable_lora=bool(adapter), max_lora_rank=16)
        self.lora = LoRARequest("adapter", 1, adapter) if adapter else None
        self.params = SamplingParams(temperature=0.0, max_tokens=max_new_tokens)

    def generate(self, schema: str, question: str) -> Generation:
        outputs = self.llm.chat(
            [build_messages(schema, question)],
            sampling_params=self.params,
            lora_request=self.lora,
        )
        completion = outputs[0].outputs[0]
        return Generation(
            sql=extract_sql(completion.text), completion_tokens=len(completion.token_ids)
        )


class OllamaBackend:
    def __init__(self, model: str, url: str, max_new_tokens: int):
        self.model = model
        self.url = url.rstrip("/")
        self.max_new_tokens = max_new_tokens

    def generate(self, schema: str, question: str) -> Generation:
        import httpx

        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "messages": build_messages(schema, question),
                "stream": False,
                "options": {"temperature": 0, "num_predict": self.max_new_tokens},
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return Generation(
            sql=extract_sql(data["message"]["content"]),
            completion_tokens=data.get("eval_count"),
        )


def make_backend(cfg) -> ModelBackend:
    if cfg.backend == "mock":
        return MockBackend()
    if cfg.backend == "transformers":
        return TransformersBackend(cfg.model_id, cfg.adapter, cfg.max_new_tokens)
    if cfg.backend == "vllm":
        return VLLMBackend(cfg.model_id, cfg.adapter, cfg.max_new_tokens)
    if cfg.backend == "ollama":
        return OllamaBackend(cfg.ollama_model, cfg.ollama_url, cfg.max_new_tokens)
    raise ValueError(f"unknown backend: {cfg.backend}")
