# Resume bullets

Fill the bracketed numbers from docs/results.md once the three Colab runs complete —
every other number below is already real.

> Built **SQLForge**, an end-to-end text-to-SQL system: fine-tuned Qwen2.5-Coder-1.5B
> with QLoRA SFT and GRPO (execution-based RL) on 8.6k Spider examples, improving
> execution accuracy from [base]% to [grpo]% on the Spider dev set — trained entirely
> on free-tier Colab T4s with resumable checkpointing.

> Designed a verifiable-reward RL pipeline: a parse-validated, read-only, timeout-
> bounded SQL executor serves as data filter, eval metric, GRPO reward and serving
> sandbox; separate per-component reward logging plus an automated audit script
> caught reward hacking (vacuous empty-result passes) before it inflated metrics.

> Shipped the model behind a FastAPI service (vLLM/GGUF backends, per-IP rate
> limiting, [p50] ms p50 latency) with a Next.js frontend and Docker Compose deploy;
> 74 offline unit tests cover the executor, metrics, rewards and API.
