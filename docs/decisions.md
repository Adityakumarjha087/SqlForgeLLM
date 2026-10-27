# Decisions

Reverse-chronological log of non-obvious technical choices: what we picked, why, and
what we considered instead.

## 2026-10-27 — Milestone 0

### Base model: Qwen/Qwen2.5-Coder-1.5B-Instruct

- **Why:** strong code/SQL prior for its size; 1.5B fits QLoRA SFT *and* GRPO (which
  needs memory for multiple sampled completions per prompt) on a free Colab T4 (16GB).
  Instruct variant means the base already follows a chat template, so the baseline eval
  is meaningful.
- **Alternatives:** Llama-3.2-1B (weaker code prior), Qwen2.5-Coder-7B (better accuracy
  but GRPO on T4 becomes painful), StarCoder2-3B (no instruct tuning).
- **Revisit if:** GRPO groups show no reward variance (model too weak → consider 3B).

### uv + src layout

- **Why uv:** single fast tool for Python pinning, venvs and lockfile; `uv sync` makes
  Colab/local/Docker installs identical. **Why `src/`:** forces installed-package imports,
  so tests can't accidentally pass by importing the working directory.

### Python 3.11

- **Why:** the ML stack (torch, TRL, bitsandbytes, Unsloth) and Colab track 3.11/3.12;
  3.13+ wheels are still patchy. Pinned via `.python-version`.

### Config: YAML + Pydantic + `SQLFORGE_*` env overrides

- **Why:** YAML files in `configs/` are reviewable and diffable per experiment; Pydantic
  validates types at load time instead of failing mid-training; env overrides let a Colab
  cell or Docker change one value (e.g. batch size) without editing tracked files.
- **Alternatives:** Hydra (overkill for one person), argparse everywhere (configs become
  unreproducible), plain dicts (typos fail silently).

### Heavy dependencies are added per-milestone

- **Why:** torch/TRL/bitsandbytes are GPU-oriented and slow to install; the local CPU
  dev loop only needs the light core. Each milestone adds exactly what it needs, keeping
  `uv sync` fast on the Mac. Seeding utility imports numpy/torch optionally for the same
  reason.

## 2026-10-27 — Milestone 1

### Spider source: HF mirror `HAL-9001/spider-databases`

- **Why:** it is the official 2024 `spider_data.zip` (questions, gold SQL, tables.json,
  all SQLite DBs) rehosted on Hugging Face; the official Google Drive link needs manual
  confirmation tokens that break scripted downloads. The script documents the manual
  Drive fallback.

### Schema format: raw CREATE TABLE statements, compact fallback

- **Why:** CREATE statements carry primary/foreign keys — exactly what the model needs
  to get joins right — and the model has seen millions of them in pretraining. They are
  whitespace-collapsed to save tokens. If a database's schema exceeds
  `max_schema_chars` (4000), we fall back to a compact `table(col type, ...)` listing:
  lossy (constraints dropped) but bounded. On Spider only a handful of DBs hit this.
- **Alternatives:** always-compact (loses FKs everywhere to fix a rare problem),
  schema linking/retrieval of relevant tables only (adds a component that can itself
  fail; out of scope for this project, noted as future work).

### Filters apply to train only; test is filtered solely for executable gold

- **Why:** dropping *hard* test examples would inflate our accuracy. The only test
  filter is "gold executes", because execution accuracy is undefined for a gold query
  that itself fails.

### Leakage defense

- Spider's train/dev database sets are disjoint by construction, but we enforce it
  anyway (`leak_guard` drops any train example using a test DB) so a future data-source
  change can't silently leak.

### `train_others.json` included

- 1659 extra examples from older datasets (GeoQuery, Restaurants, ...) ported to
  Spider format. More SFT signal for free; the same execution filter applies. Config
  flag `include_train_others` turns it off for ablations.

## 2026-10-27 — Milestone 3 (SFT)

### Why completion-only loss

The prompt (schema + question) is ~3-4x longer than the target SQL. With full-sequence
loss, most of the gradient teaches the model to predict schema text it will never have
to generate, and the SQL signal is diluted. TRL's prompt-completion format masks prompt
tokens out of the loss so every gradient step is about question -> SQL.

### Hyperparameters and why

| Param | Value | Why |
|---|---|---|
| LoRA rank r | 16 | enough capacity for a narrow task (SQL syntax + schema grounding); r=8 underfit slightly in literature, r=64 doubles memory for little gain on 1.5B |
| alpha | 32 | standard 2x rank; effective scale alpha/r = 2 |
| target modules | all attn + MLP proj | attention-only LoRA underperforms on structured generation tasks |
| dropout | 0.05 | mild; dataset is small-ish (8.6k) |
| LR | 2e-4, cosine, 3% warmup | the usual LoRA sweet spot — LoRA tolerates ~10x higher LR than full FT |
| epochs | 2 | 1 underfits small data; 3+ memorizes train schemas |
| max_seq_len | 1024 | covers schema (~400 tok) + question + SQL for ~99% of examples |
| batch | 4 x 4 accum = 16 effective | largest that fits T4 with grad checkpointing |
| precision | fp16 + 4-bit nf4 base | T4 (compute 7.5) has no bf16 |

### Memory math (why QLoRA on a 16GB T4)

Full fp16 fine-tune of 1.54B params: 2 (weights) + 2 (grads) + 8 (Adam m,v in fp32)
= 12 bytes/param ≈ **18.5GB** — does not fit, before activations.

QLoRA: base in 4-bit nf4 ≈ 1.0GB; LoRA params (r=16, all proj) ≈ 35M -> 70MB fp16;
their grads + paged 8-bit Adam ≈ 0.3GB; activations at batch 4 x 1024 tokens with
gradient checkpointing ≈ 2-3GB; CUDA/kernel overhead ≈ 1.5GB. **Total ≈ 5-6GB** —
comfortable, with headroom for the eval pass.

### Plain TRL + PEFT + bitsandbytes, not Unsloth

Unsloth is ~2x faster but pins specific torch/CUDA combos and monkey-patches
internals; on a portfolio project, readable standard-stack code wins. If T4 time
becomes the bottleneck, swapping the model-loading block for Unsloth's
FastLanguageModel is a contained change.

## 2026-10-27 — Milestone 4 (GRPO)

### Reward weighting: format 0.2, execution 0.3, correctness 1.0, degenerate ≤ 0

Correctness must dominate: 0.2 + 0.3 = 0.5 < 1.0, so no amount of well-formed,
runnable-but-wrong SQL outscores a correct answer. Format and execution exist as
*shaping*: with correctness alone, a prompt where all 8 samples are wrong gives zero
advantage everywhere and teaches nothing; partial credit for "parses" and "runs"
creates within-group variance even when nothing is correct yet. The degenerate
penalty (empty / overlong / repetition collapse) targets the failure modes small
models find first under RL. Each component is a separate TRL reward function so it
gets its own logged curve — the reward-hacking tell is format/execution rising while
correctness is flat.

### Why GRPO starts from the SFT adapter and the KL anchors to it

RL can only reinforce behaviour the policy already exhibits sometimes. The base model
rarely emits perfectly-formatted correct SQL at temperature 0.9, so groups would be
uniformly wrong (zero advantage). The SFT adapter is both the starting policy and the
KL reference (beta=0.04): rewards pull toward correctness, KL pulls back toward
SFT-style output, preventing collapse into degenerate high-reward text.

### Sizing for a T4

2000 prompts x 8 generations, completion ≤192 tokens, 4-bit base + LoRA. GRPO's
per-step cost is dominated by generation (8 samples/prompt) and reward evaluation
(2 SQLite executions/sample, bounded by the 5s timeout). ~500 optimizer steps fits
in 2-3 free sessions with checkpoint resume. See docs/grpo-explained.md for the
GRPO vs PPO vs DPO background.

## 2026-10-27 — Milestone 6 (serving)

### Backend abstraction: vLLM / transformers / Ollama / mock behind one protocol

vLLM where there's a GPU (continuous batching, 10x+ throughput); plain transformers
anywhere torch runs; Ollama for a laptop-friendly CPU demo; a deterministic mock so
API tests and frontend development never need a model. Chosen per deployment via
`SQLFORGE_BACKEND`, so the same image serves all roles.

### LoRA merge + GGUF path (for the CPU/Ollama backend)

1. `scripts/merge_adapter.py` folds the LoRA delta into the base weights
   (W' = W + (alpha/r)·BA) — GGUF tooling consumes full checkpoints, not adapters.
2. llama.cpp `convert_hf_to_gguf.py` -> fp16 GGUF; `llama-quantize` -> Q8_0.
   **Q8_0, not Q4_K_M:** a 1.5B model is disproportionately damaged by 4-bit
   post-training quantization, and at 1.6GB the Q8 file is still trivially laptop-sized.
3. `ollama create sqlforge -f Modelfile` (FROM the .gguf) and set
   `SQLFORGE_BACKEND=ollama`.

### Security

The model's SQL is never trusted: execution goes through the same safe executor as
eval (parse-validated single SELECT, read-only connection, 5s timeout, row cap).
`db_id` is pattern-validated and must exist on disk (no path input). Question length
capped. Hand-rolled per-IP token bucket (~20 lines) instead of a middleware
dependency — small enough to read in an interview, swap for Redis-based limiting
behind a real load balancer.

### Databases mounted, not baked into the image

Keeps the image small and the data pipeline the single source of truth for what the
API can query.
