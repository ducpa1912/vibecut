# Local small models for script rewriting

For the rewrite stage the job is narrow: read a short video transcript, keep the
facts, and write N lines with per-line time budgets in a target language. Small
models are enough if the context is prepared for them.

## Comparison

| | Qwen2.5-3B Instruct (`qwen2.5:3b`) | Llama 3.2 3B Instruct | Gemma 3 1B IT | Qwen2.5-3B Instruct 4-bit (MLX) | Apple FM on-device ~3B |
|---|---|---|---|---|---|
| Parameters | 3.1B | 3.2B | 1B | 3.1B | ~3B |
| Disk (quantized) | ~1.9 GB (Q4_K_M) | ~2.0 GB (Q4_K_M) | ~0.8 GB (Q4) | ~1.7 GB (4-bit MLX) | 0 MB app, ~4-8 GB Apple Intelligence system assets |
| RAM at run | ~2.5–3 GB | ~2.5–3 GB | ~1–1.5 GB | ~2–2.5 GB | ~2–3 GB |
| Context | 32k | 128k | 32k | 32k | ~4k on M1/M2 |
| Languages | 29+ | 8 official (en, de, fr, it, pt, hi, es, th) | 140+ claimed | 29+ | Apple Intelligence languages |
| JSON / structured output | strong | good | weaker, needs retries | strong | strong via guided generation |
| Speed on M1 (rough) | 12–25 tok/s CPU | 12–25 tok/s CPU | 35–60 tok/s CPU | 25–40 tok/s GPU | 20–40 tok/s |
| License | Apache-2.0 | Llama 3.2 Community | Gemma Terms | Apache-2.0 | Apple terms, on-device only |
| Install | `ollama pull qwen2.5:3b` | `ollama pull llama3.2:3b` | `ollama pull gemma3:1b` | `pip install mlx-lm` | enable Apple Intelligence |

Rough speeds are token rates on an M1 with a short prompt; treat as guidance,
not a benchmark.

## How VibeCut uses them

1. Translate the full transcript once into the target language (memoized).
2. Ask the small model for a **story brief** (topic, audience, promise, proof,
   tone, hook idea, payoff idea) and cache it.
3. For each beat, retrieve only the ~8 most relevant transcript sentences
   (BM25-lite) and send brief + lines + role + seconds budget to the model.
4. Validate the result: budgets, no invented numbers, no filler; fall back to
   rules if the model drifts.

This keeps the prompt in the 1.5–3k token range, which is where 1B–3B models
stay coherent.

## Recommendations

- Default: **Qwen2.5-3B via MLX** — fastest local path, multilingual, Apache-2.0.
- Server-style or mixed tools: **Ollama qwen2.5:3b**.
- Low-RAM / oldest M1: **Gemma 3 1B**, with the rules fallback close by.
- Targets limited to the 8 Llama languages: **Llama 3.2 3B** has the best
  instruction following of the 3B group.
- Zero install and best structured output: **Apple FM**, when Apple Intelligence
  is enabled; context is small, so the brief+retrieval design matters most here.
