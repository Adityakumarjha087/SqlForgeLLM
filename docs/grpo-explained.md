# GRPO vs PPO vs DPO — and why GRPO fits SQL generation

## The problem all three solve

After SFT, the model imitates training examples. But imitation can't teach "your query
*ran and returned the wrong rows*" — that signal only exists if you score complete
generated outputs. RL fine-tuning methods optimize the model against such a score.

## PPO (Proximal Policy Optimization)

The classic RLHF algorithm. For each prompt, sample a completion, score it with a reward
model, and estimate *advantage* ("was this better than expected?") using a separate
**value network** — a second full copy of the model trained alongside the policy to
predict expected reward. Plus a frozen reference model for the KL penalty.

- Cost: 3 models in memory (policy, value, reference). On a T4 with a 1.5B model: hopeless.
- The value network is also the main source of instability — if its estimates are bad,
  the advantages are noise.

## DPO (Direct Preference Optimization)

Skips RL entirely. Take *pairs* of outputs (chosen, rejected) for the same prompt and
directly raise the likelihood of chosen over rejected with a classification-style loss.

- Beautifully simple and stable, but it needs **preference pairs**, and it only ever
  compares two static samples. Our signal isn't "A is better than B" from a human —
  it's an executable test. Converting execution results into static pairs throws away
  most of the information and can't iterate: DPO never samples *new* queries during
  training, so it can't explore its way to queries that pass.

## GRPO (Group Relative Policy Optimization)

PPO's update rule, but the value network is replaced by a **group baseline**: sample
G completions (we use 8) for the *same* prompt, score each, and define each sample's
advantage as its reward relative to the group mean (normalized by the group std).
"Better than your siblings" replaces "better than a learned prediction".

- Memory: policy + frozen reference only — fits a T4 alongside 4-bit weights.
- No value network to go wrong.
- The baseline is exact for that prompt, not an approximation.

## Why GRPO is the right fit for verifiable rewards like SQL execution

1. **The reward is a program, not a model.** We execute the generated SQL and compare
   result sets with the gold query. No reward model to train, no reward-model bias to
   fight — the classic use case GRPO became known for (DeepSeek-R1 math/code training).
2. **Group-relative scoring handles sparse binary rewards.** "Correct: 0 or 1" is a
   brutal signal for PPO's value net. In a GRPO group, if 2 of 8 samples are correct,
   those two get positive advantage and the other six negative — a clean, local learning
   signal from a sparse reward.
3. **It samples fresh outputs every step** (unlike DPO), so the model can discover
   query shapes that never appeared in SFT data, and immediately gets graded on them.

## The catch, honestly

- If **all 8 samples get the same reward** (all wrong on a hard prompt, all right on an
  easy one), advantages are zero and the prompt teaches nothing — wasted compute. This
  is why we sample at temperature 0.9 and why GRPO works best *after* SFT, when some
  samples succeed.
- **Reward hacking:** the model optimizes the reward you wrote, not the one you meant.
  Example: queries whose result is an empty set match a gold query that also returns
  empty — reward 1.0 for `SELECT ... WHERE 1=0`-style degenerate answers on some
  examples. This is why each reward component is logged separately and why we manually
  inspect 30 outputs after training (`scripts/inspect_outputs.py`).
- **KL still matters.** Without the beta*KL anchor to the SFT reference, a 1.5B model
  happily collapses into degenerate high-reward text.
