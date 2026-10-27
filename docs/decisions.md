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
