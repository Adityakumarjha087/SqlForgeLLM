"""Merge a LoRA adapter into the base model and save full weights.

Needed before GGUF conversion (llama.cpp consumes merged HF checkpoints) and
for vLLM deployments that prefer merged weights over runtime LoRA.

Usage:
  uv run python scripts/merge_adapter.py --adapter outputs/grpo/adapter \\
      --out outputs/merged

Then (GGUF, documented in docs/decisions.md):
  git clone https://github.com/ggerganov/llama.cpp
  python llama.cpp/convert_hf_to_gguf.py outputs/merged --outfile sqlforge.gguf
  llama.cpp/build/bin/llama-quantize sqlforge.gguf sqlforge-q8.gguf Q8_0
  ollama create sqlforge -f Modelfile   # FROM ./sqlforge-q8.gguf
"""

import argparse

from sqlforge.eval.generate import load_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # load_model already merges the adapter (merge_and_unload) into full weights.
    lm = load_model(args.model, adapter_path=args.adapter, device="cpu")
    lm.model.save_pretrained(args.out)
    lm.tokenizer.save_pretrained(args.out)
    print(f"Merged model saved to {args.out}")


if __name__ == "__main__":
    main()
