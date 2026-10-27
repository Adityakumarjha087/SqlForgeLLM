"""Model loading and batched greedy generation for evaluation.

torch/transformers are imported lazily so the rest of the package works in the
light CPU environment; install the `ml` dependency group to use this module.
"""

from dataclasses import dataclass

from tqdm import tqdm

from sqlforge.data.prompting import build_messages, extract_sql


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class LoadedModel:
    model: object
    tokenizer: object
    device: str


def load_model(model_id: str, adapter_path: str | None = None, device: str | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = device or pick_device()
    dtype = torch.float32 if device == "cpu" else torch.bfloat16
    tokenizer = AutoTokenizer.from_pretrained(model_id, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    if adapter_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter_path)
        model = model.merge_and_unload()
    model.to(device)
    model.eval()
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return LoadedModel(model=model, tokenizer=tokenizer, device=device)


def generate_sql(
    lm: LoadedModel,
    examples: list,
    batch_size: int = 8,
    max_new_tokens: int = 256,
) -> list[str]:
    """Greedy, batched generation; returns one extracted SQL string per example."""
    import torch

    tokenizer, model = lm.tokenizer, lm.model
    predictions: list[str] = []
    for start in tqdm(range(0, len(examples), batch_size), desc="generate", unit="batch"):
        batch = examples[start : start + batch_size]
        prompts = [
            tokenizer.apply_chat_template(
                build_messages(ex.schema, ex.question),
                tokenize=False,
                add_generation_prompt=True,
            )
            for ex in batch
        ]
        inputs = tokenizer(prompts, return_tensors="pt", padding=True).to(lm.device)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        completions = tokenizer.batch_decode(
            output[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )
        predictions.extend(extract_sql(c) for c in completions)
    return predictions
