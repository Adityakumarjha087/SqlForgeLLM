# SQLForge

A portfolio project for an AI Engineer job switch: fine-tune a small open LLM for
text-to-SQL with SFT and then GRPO (RL with verifiable rewards), evaluate it rigorously,
and ship it behind an API with a small web frontend. The owner wants to deeply understand
every part — explain decisions, teach concepts when asked, and write things down.

## Goal

Given a natural-language question and a database schema, generate a correct SQLite query.
Show a measurable improvement chain: **base model → SFT → SFT+GRPO**, measured by
execution accuracy on the Spider dev set.

## Constraints

- **Compute:** free Google Colab (T4, 16GB VRAM) for all training and full evals.
  Everything must also run on a local CPU (Mac) for development and smoke tests.
- **Base model:** `Qwen/Qwen2.5-Coder-1.5B-Instruct` (small enough for QLoRA + GRPO on a
  T4; good code prior). Keep the model id in config so it can be swapped.
- **Dataset:** Spider 1.0 (train for SFT/GRPO, official dev set as our held-out test set).
  No test databases may leak into training.
- **Budget:** $0. Free tiers only.

## Tech stack

- Python 3.11+, `uv` for env/deps, `ruff` for lint+format, `pytest` for tests.
- `transformers`, `peft`, `trl` (SFTTrainer, GRPOTrainer), `bitsandbytes`/Unsloth for QLoRA.
- `sqlglot` for SQL parsing/analysis, `sqlite3` stdlib for execution.
- `datasets` + JSONL files for data. `matplotlib` for charts.
- Serving: FastAPI + Pydantic; vLLM on GPU, llama.cpp/Ollama (GGUF) on CPU; Docker.
- Frontend: Next.js + TypeScript in `web/`.

## Repo layout

```
sqlforge/
  configs/          # yaml configs (data.yaml, sft.yaml, grpo.yaml, eval.yaml, serve.yaml)
  src/sqlforge/     # package: config loader, seeding, data, eval, serving
  training/         # sft.py, grpo.py, rewards.py
  scripts/          # download_spider.py, run_eval.py, benchmarks
  notebooks/        # thin Colab wrappers: 01_baseline_eval, 02_sft, 03_grpo
  tests/            # pytest, tiny fixtures (mini SQLite DBs, small JSONL samples)
  data/             # gitignored: raw/ and processed/
  docs/             # decisions.md, results.md, failures.md, assets/ (charts)
  web/              # Next.js frontend (Milestone 7)
```

## Milestones

0. Project setup: uv, pyproject, ruff, pytest, folders, .gitignore, .env.example,
   README skeleton, config loader, seeding utility.
1. Data pipeline: download Spider + SQLite DBs, prompt template with schema
   (CREATE TABLE statements, trimmed), quality filters (dedupe, sqlglot parse,
   executes within timeout) with per-filter drop counts, leak-safe splits, JSONL output,
   data report in docs/results.md.
2. Eval harness + baseline: safe read-only SQLite executor (timeout, row limit,
   SELECT-only), execution accuracy (order-insensitive unless gold has ORDER BY) +
   exact match, run_eval.py with greedy decoding and batching, CPU smoke test (20 ex),
   Colab notebook for full baseline.
3. SFT: TRL SFTTrainer + PEFT (QLoRA), completion-only loss (mask prompt tokens),
   fits on T4, memory math in docs/decisions.md, eval after training.
4. GRPO: unit-tested reward functions (format, execution, correctness, degenerate-output
   penalties), TRL GRPOTrainer sized for T4, per-component reward logging + KL +
   completion length, base-vs-SFT-vs-GRPO comparison, reward-hacking inspection of 30
   outputs logged in docs/failures.md.
5. Error analysis: per-SQL-feature categories via sqlglot on gold queries + Spider
   difficulty, accuracy per category per model, charts in docs/assets/, 5-6 findings.
6. Serving: FastAPI (/generate-sql, /query, /health), vLLM or GGUF fallback, LoRA merge +
   quantization documented, security (read-only, timeouts, length limits, rate limiting),
   Dockerfile + compose, latency benchmark (p50/p95, tok/s), mocked-model tests.
7. Frontend: Next.js app — pick sample DB, see schema, ask question, view SQL
   (highlighted) + result table + latency; mobile-friendly; added to docker-compose.
8. Polish: README with architecture diagram (Mermaid), results table, charts, repro steps,
   limitations; repo cleanup; resume bullets with real numbers; interview Q&A.

## Working conventions

- Plan first for every milestone; wait for approval before implementing.
- Every non-obvious technical choice gets a short entry in `docs/decisions.md`
  (what, why, alternatives considered).
- All metrics/results land in `docs/results.md`; surprises and failures in
  `docs/failures.md`. Never overwrite old results — append with date + commit hash.
- Determinism: single seeding utility used everywhere; greedy decoding for eval.
- Tests use tiny fixtures (no network, no real model). Anything touching the real
  model/dataset lives behind scripts or notebooks, not tests.
- Keep Colab notebooks thin: clone repo, install, call into `src/`/`training/`/`scripts/`.
  No logic lives only in a notebook.
- Secrets (HF token, W&B key) via .env; never committed.
