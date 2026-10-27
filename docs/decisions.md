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
