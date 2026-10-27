# Decision-model access, credits, and pilot budget

Initial access research checked October 10, 2026 (Pacific time). No account was created, credits purchased, or message sent during that research. Live pilot requests were subsequently made with the owner's configured OpenRouter key; actual costs are recorded with each run. Confirm the available OpenRouter balance before larger paid experiments.

## Access through OpenRouter

Use one OpenRouter account, API key, and credit balance for all four remote models. The listed model IDs and rates are:

| Model | OpenRouter model ID | Input rate per million tokens | Output rate per million tokens |
| --- | --- | ---: | ---: |
| [Jev 1.13](https://openrouter.ai/typesafe/jev-1.13) | `typesafe/jev-1.13` | $0.042 | $0 |
| [GPT-6 Luna Decisions](https://openrouter.ai/openai/gpt-6-luna-decisions) | `openai/gpt-6-luna-decisions` | $0.10 | $0 |
| [Microsoft-Decision-1](https://openrouter.ai/microsoft/microsoft-decision-1) | `microsoft/microsoft-decision-1` | $0.042 | $0 |
| [GPT-6.1 Sol](https://openrouter.ai/openai/gpt-6.1-sol) (medium reasoning) | `openai/gpt-6.1-sol` | $2 | $10 |

Jev, Luna, and Microsoft are structured decision models: supply the same legal action options and observation to each, then select the returned choice. They use OpenRouter's [Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request). Sol medium reasoning is a chat model using the same question and state with a strict JSON choice schema; its reasoning output creates a material additional cost. Live smoke tests succeeded for all four remote controllers. Microsoft says its weights change continually even when the API shape remains stable. Save model ID, provider, request date, response metadata, and billed usage for every run; state when an immutable version cannot be pinned.

OpenRouter's [pricing page](https://openrouter.ai/pricing) currently lists a 5.5% platform fee for standard credit purchases. Check the actual checkout total and any applicable taxes before topping up. Promotional credits from a direct provider should not be assumed to appear in OpenRouter's balance.

## Estimated API cost

Illustrative assumptions: a 600-second evaluation window, a decision every second, and **1,500 billed input tokens per call**, including the observation, instructions, and action definitions. That is 600 calls and 900,000 tokens per episode per provider. Measure real token usage in the pilot.

These estimates cover only the three Decisions models, one junction, and one API call per update. Sol medium reasoning is excluded because its output-token and reasoning-token usage varies greatly by state. Two decentralized junction controllers making separate calls approximately double the token cost at the same observation size. A centralized joint-action request needs a measured estimate for its larger state and action descriptions. The proposed 1 Hz update rate follows the new primary reference, TR2023-059.

| Episodes per API controller | Calls per model | Input tokens per model | Jev | Luna Decisions | Microsoft-Decision-1 | Three-model total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 12,000 | 18 million | $0.76 | $1.80 | $0.76 | $3.31 |
| 100 | 60,000 | 90 million | $3.78 | $9.00 | $3.78 | $16.56 |
| 1,000 | 600,000 | 900 million | $37.80 | $90.00 | $37.80 | $165.60 |

Totals use unrounded line-item costs. These are calculated token costs, not account purchase minimums. They exclude the platform credit-purchase fee, drain-period decisions, frozen-state evaluation, retries, repeated runs, taxes, and any applicable processing premiums. Larger states increase costs proportionally.

**Recommendation:** check the OpenRouter balance and use any available credits for a small smoke test, then cap the 20-episode three-model pilot near its estimated $3.31 token cost plus measured overhead. A 100-episode study is estimated at $16.56 in model tokens, and a 1,000-episode campaign at $165.60. Measure actual usage and end-to-end latency before expanding; advertised latency and calibrated confidence may not transfer to this control task.

## Optional direct Jev credits

TypeSafe's [official model documentation](https://docs.typesafe.ai/models) lists `jev-1.13.0` at $0.042 per million input tokens with free output tokens. Its [customer agreement, Section 8.2](https://typesafe.ai/legal/mca), describes discretionary promotional credits, but no public academic-credit program or guaranteed signup balance was found. A direct TypeSafe account and any credits it receives are separate from OpenRouter. If the project later needs direct access, use the [official console](https://console.typesafe.ai/) and [contact page](https://typesafe.ai/contact) to ask about $10-$25 in research evaluation credits, version pinning, limits, expiry, and eligibility.
