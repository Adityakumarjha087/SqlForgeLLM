# Interview Q&A

Ten questions this project invites, with answers grounded in what was actually built.

### 1. Why execution accuracy instead of exact match?

Exact match punishes semantically identical SQL (`count(*)` vs `count(concert_id)`,
join order, aliasing) and rewards memorizing gold phrasing. Execution accuracy asks
the only question users care about: did the query return the right rows? We report
exact match as a secondary metric, and we're honest about execution accuracy's false
positives — a wrong query can luck into the right rows on one database state — which
is why the standard fix (test-suite eval over DB variants) is named in future work.

### 2. How do you know your test set is clean?

Three mechanisms: Spider's dev set uses databases disjoint from train by construction;
our `leak_guard` filter re-enforces that on every pipeline run (dropping any train
example whose db appears in test); and a unit test pins the behaviour. We also never
quality-filter the test set (that would inflate scores) — the only test filter is
"gold executes", without which the metric is undefined.

### 3. Why GRPO and not PPO or DPO?

PPO needs a trained value network (a second model) plus policy and reference — 3
models won't fit a free T4, and the value net is the least stable part. DPO needs
static preference pairs and never samples during training, so it can't explore its
way to queries that pass. GRPO replaces the value net with a group baseline: sample 8
completions per prompt, advantage = reward relative to the group mean. That fits our
compute and — crucially — our reward is *verifiable* (execute the SQL), the exact
setting GRPO is known for. Full write-up: docs/grpo-explained.md.

### 4. How did you guard against reward hacking?

Three layers. Design: correctness (1.0) outweighs format + execution combined (0.5),
so cosmetic rewards can't beat being right, and degenerate outputs (empty, overlong,
repetition) are penalized. Observability: each reward is a separate TRL function, so
each gets its own logged curve — format rising while correctness is flat is the tell.
Audit: `scripts/inspect_outputs.py` samples 30 outputs post-training and auto-flags
suspicious passes (e.g. *vacuous passes* where gold and prediction both return empty
results — the metric can't distinguish a right query from garbage there).

### 5. Why does GRPO start from the SFT checkpoint?

RL can only reinforce behaviour the policy already samples. At temperature 0.9 the
base model rarely emits a fully correct query, so all 8 group samples would get the
same (zero) reward — zero advantage, zero gradient. After SFT, some samples succeed,
and group-relative scoring turns that variance into signal. The SFT policy is also
the KL reference that keeps the policy from collapsing into degenerate high-reward
text.

### 6. Walk me through the memory math for training on a 16GB T4.

Full fp16 fine-tune: 1.54B params × (2B weights + 2B grads + 8B Adam state) ≈ 18.5GB
— doesn't fit before activations. QLoRA: 4-bit nf4 base ≈ 1GB, LoRA adapters (r=16,
all attention+MLP projections, ~35M params) ≈ 70MB, grads + paged 8-bit Adam only on
those ≈ 0.3GB, activations at batch 4 × 1024 with gradient checkpointing ≈ 2-3GB.
Total ≈ 5-6GB. fp16 (not bf16) because T4 is compute capability 7.5.

### 7. Why completion-only loss in SFT?

The prompt (schema + question) is 3-4× longer than the SQL target. Full-sequence loss
spends most of the gradient teaching the model to predict schema text it never has to
generate. Masking prompt tokens concentrates every update on the question→SQL mapping.

### 8. How do you safely execute model-generated SQL?

Never trust the model: sqlglot-parse the output and require exactly one SELECT-shaped
statement (no string matching, no PRAGMA/ATTACH/multi-statement tricks); open SQLite
read-only (`mode=ro` URI) as a second layer; interrupt via progress handler after a
deadline (SQLite has no native query timeout); cap returned rows. The same executor
is reused as data filter, eval metric, GRPO reward and serving sandbox, so it's
tested once and trusted everywhere.

### 9. What breaks on free Colab, and how did you design around it?

Sessions die after a few hours and GPUs are rationed. Every training script
checkpoints every 50-100 steps to Drive and auto-resumes from the last checkpoint;
runs are sized to fit sessions (SFT ~2h; GRPO split across 2-3 sessions); notebooks
are thin wrappers so no logic exists only in Colab; and the whole repo installs
identically everywhere via uv's lockfile.

### 10. Your eval found the base model already decent. Why fine-tune at all?

The instruct base is good at *easy* SQL; the per-category analysis shows where it
falls apart (nested queries, multi-join, 'extra' difficulty). SFT fixes format and
schema-grounding; GRPO specifically optimizes the executable-correctness objective
SFT can't see. The comparison table and per-category charts quantify exactly what
each stage bought — that measured chain, not any single number, is the point of the
project.
