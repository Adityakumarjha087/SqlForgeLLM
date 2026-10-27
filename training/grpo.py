"""Milestone 4: GRPO on top of the SFT model, rewards = real SQL execution.

Starts from the SFT adapter (never the base model: GRPO can only reinforce
behaviour the policy already samples sometimes). TRL logs each reward component
separately (rewards/<func_name>/mean), plus KL and completion length - watch
format/execution rising while correctness stays flat: that is reward hacking.

Resumable: re-running with the same output_dir picks up the latest checkpoint.

Usage: uv run python training/grpo.py [--config configs/grpo.yaml]
"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from sqlforge.config import load_config
from sqlforge.data.pipeline import read_jsonl
from sqlforge.data.prompting import build_messages
from sqlforge.seeding import set_seed
from training.rewards import make_reward_funcs

REPO_ROOT = Path(__file__).resolve().parents[1]


class GRPOTrainConfig(BaseModel):
    model_id: str
    sft_adapter: str
    train_path: str
    db_root: str
    output_dir: str
    num_prompts: int
    max_prompt_length: int
    max_completion_length: int
    num_generations: int
    temperature: float
    learning_rate: float
    beta: float
    epochs: int
    per_device_batch: int
    grad_accum: int
    load_in_4bit: bool
    seed: int
    exec_timeout_s: float
    exec_row_limit: int
    logging_steps: int
    save_steps: int
    report_to: str


def build_prompt_dataset(cfg: GRPOTrainConfig, tokenizer):
    """Prompt-only dataset; db_id and gold ride along for the reward functions."""
    from datasets import Dataset

    examples = read_jsonl(REPO_ROOT / cfg.train_path)
    rows = [
        {
            "prompt": tokenizer.apply_chat_template(
                build_messages(ex.schema, ex.question),
                tokenize=False,
                add_generation_prompt=True,
            ),
            "db_id": ex.db_id,
            "gold": ex.query,
        }
        for ex in examples
    ]
    dataset = Dataset.from_list(rows).shuffle(seed=cfg.seed)
    return dataset.select(range(min(cfg.num_prompts, len(dataset))))


def load_policy(cfg: GRPOTrainConfig):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(cfg.model_id, padding_side="left")
    kwargs: dict = {"dtype": torch.float16}
    if cfg.load_in_4bit:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(cfg.model_id, **kwargs)
    # Continue training the SFT adapter weights; they are also the KL reference.
    model = PeftModel.from_pretrained(model, str(REPO_ROOT / cfg.sft_adapter), is_trainable=True)
    return model, tokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "grpo.yaml"))
    args = parser.parse_args()
    cfg = load_config(args.config, GRPOTrainConfig)
    set_seed(cfg.seed)

    from transformers.trainer_utils import get_last_checkpoint
    from trl import GRPOConfig, GRPOTrainer

    model, tokenizer = load_policy(cfg)
    dataset = build_prompt_dataset(cfg, tokenizer)
    output_dir = REPO_ROOT / cfg.output_dir

    grpo_config = GRPOConfig(
        output_dir=str(output_dir),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.per_device_batch,
        gradient_accumulation_steps=cfg.grad_accum,
        gradient_checkpointing=True,
        learning_rate=cfg.learning_rate,
        beta=cfg.beta,
        num_generations=cfg.num_generations,
        temperature=cfg.temperature,
        max_prompt_length=cfg.max_prompt_length,
        max_completion_length=cfg.max_completion_length,
        fp16=True,
        optim="paged_adamw_8bit" if cfg.load_in_4bit else "adamw_torch",
        logging_steps=cfg.logging_steps,
        save_steps=cfg.save_steps,
        save_total_limit=2,
        log_completions=True,
        report_to=cfg.report_to,
        seed=cfg.seed,
    )
    trainer = GRPOTrainer(
        model=model,
        args=grpo_config,
        train_dataset=dataset,
        reward_funcs=make_reward_funcs(
            db_root=REPO_ROOT / cfg.db_root,
            timeout_s=cfg.exec_timeout_s,
            row_limit=cfg.exec_row_limit,
        ),
        processing_class=tokenizer,
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
