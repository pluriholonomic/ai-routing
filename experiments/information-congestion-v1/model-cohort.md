# Frozen open-weight model cohort

Frozen before the prospective start: 2026-07-23 00:00 UTC.

The cohort was selected from the immutable Hugging Face revision
`6d7d101713f603ca2e5aca71cfd29b29d67fddad`. The pre-period panel ends at
2026-07-22 04:02:43 UTC and contains 3,274 distinct endpoint capture clocks.
Qualification required at least four positive-price providers, at least two
providers with two price changes and 70% panel coverage, and downloadable
weights published by the model author. No paid outcome was available or used.

| OpenRouter model ID | Latest positive-price providers | Pre-period responsive providers | Final live shadow menu `n` | Final live responsive `k` |
|---|---:|---:|---:|---:|
| `z-ai/glm-5.2` | 28 | 11 | 28 | 9 |
| `openai/gpt-oss-120b` | 18 | 3 | 18 | 2 |
| `google/gemma-4-31b-it` | 15 | 3 | 15 | 1 |
| `minimax/minimax-m2.7` | 11 | 3 | 11 | 0 |
| `deepseek/deepseek-v4-flash` | 19 | 2 | 19 | 2 |
| `deepseek/deepseek-v4-pro` | 17 | 2 | 17 | 2 |
| `moonshotai/kimi-k2.7-code` | 13 | 2 | 13 | 1 |

The historical qualification count and live count differ because the plan
intersects the fixed pre-period classification with the current compatible
endpoint menu. That intersection is deliberate: disappeared providers are not
reclassified or replaced using outcomes.

Author-weight sources:

- [Z.ai GLM-5.2 weights](https://huggingface.co/zai-org/GLM-5.2)
- [OpenAI GPT-OSS open-weight documentation](https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss)
- [Google Gemma 4 model documentation](https://ai.google.dev/gemma/docs/core)
- [MiniMax M2.7 author weights](https://huggingface.co/MiniMaxAI/MiniMax-M2.7)
- [DeepSeek V4 author collection](https://huggingface.co/collections/deepseek-ai/deepseek-v4)
- [Moonshot Kimi-K2.7-Code weights](https://huggingface.co/moonshotai/Kimi-K2.7-Code)

The list is immutable for v1. Availability failures remain visible in the run
ledger; they do not trigger post-start model substitution.
