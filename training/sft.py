"""Milestone 3: LoRA SFT on the processed Spider training set.

Loss is computed on the SQL completion only (prompt tokens are masked): we use
TRL's prompt-completion dataset format, where ``completion_only_loss`` defaults
to true. Training the model to also predict the prompt (schema + question)
would spend most of the gradient on text the model never has to produce, and
rewards it for memorizing schemas instead of mapping question -> SQL.

Runs on a free Colab T4. Resumable: re-running with the same output_dir picks
up the latest checkpoint automatically.

Usage: uv run python training/sft.py [--config configs/sft.yaml]
"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from sqlforge.config import load_config
from sqlforge.data.pipeline import read_jsonl
from sqlforge.data.prompting import build_messages
from sqlforge.seeding import set_seed

REPO_ROOT = Path(__file__).resolve().parents[1]


class SFTTrainConfig(BaseModel):
    model_id: str
    train_path: str
    output_dir: str
    val_fraction: float
    max_seq_len: int
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    target_modules: list[str]
    load_in_4bit: bool
    learning_rate: float
    epochs: int
    per_device_batch: int
    grad_accum: int
    warmup_steps: int
    fp16: bool
    lr_scheduler: str
    seed: int
    logging_steps: int
    save_steps: int
    report_to: str


def build_prompt_completion_dataset(cfg: SFTTrainConfig, tokenizer):
    """JSONL -> HF Dataset of {prompt, completion} strings."""
    from datasets import Dataset

    examples = read_jsonl(REPO_ROOT / cfg.train_path)
    rows = [
        {
            "prompt": tokenizer.apply_chat_template(
                build_messages(ex.schema, ex.question),
                tokenize=False,
                add_generation_prompt=True,
            ),
            "completion": ex.query,
        }
        for ex in examples
    ]
    dataset = Dataset.from_list(rows).shuffle(seed=cfg.seed)
    return dataset.train_test_split(test_size=cfg.val_fraction, seed=cfg.seed)


def load_base_model(cfg: SFTTrainConfig):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(cfg.model_id)
    kwargs: dict = {"dtype": torch.float16}  # T4 has no bf16
    if cfg.load_in_4bit:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(cfg.model_id, **kwargs)
    return model, tokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "sft.yaml"))
    args = parser.parse_args()
    cfg = load_config(args.config, SFTTrainConfig)
    set_seed(cfg.seed)

    from peft import LoraConfig
    from transformers.trainer_utils import get_last_checkpoint
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = load_base_model(cfg)
    splits = build_prompt_completion_dataset(cfg, tokenizer)
    output_dir = REPO_ROOT / cfg.output_dir

    peft_config = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=cfg.target_modules,
        task_type="CAUSAL_LM",
    )
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        max_length=cfg.max_seq_len,
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.per_device_batch,
        per_device_eval_batch_size=cfg.per_device_batch,
        gradient_accumulation_steps=cfg.grad_accum,
        gradient_checkpointing=True,
        learning_rate=cfg.learning_rate,
        lr_scheduler_type=cfg.lr_scheduler,
        warmup_steps=cfg.warmup_steps,
        fp16=cfg.fp16,
        optim="paged_adamw_8bit" if cfg.load_in_4bit else "adamw_torch",
        logging_steps=cfg.logging_steps,
        eval_strategy="steps",
        eval_steps=cfg.save_steps,
        save_steps=cfg.save_steps,
        save_total_limit=2,
        report_to=cfg.report_to,
        seed=cfg.seed,
    )
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=splits["train"],
        eval_dataset=splits["test"],
        peft_config=peft_config,
    )

    last_checkpoint = get_last_checkpoint(str(output_dir)) if output_dir.exists() else None
    if last_checkpoint:
        print(f"Resuming from {last_checkpoint}")
    trainer.train(resume_from_checkpoint=last_checkpoint)

    adapter_dir = output_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    (output_dir / "log_history.json").write_text(json.dumps(trainer.state.log_history, indent=2))
    print(f"Adapter saved to {adapter_dir}")


if __name__ == "__main__":
    main()
