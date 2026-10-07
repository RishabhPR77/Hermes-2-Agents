# Scoring — how the Strategist picks a topic

Score each candidate out of 100 against the weights below. Rate each factor
1–5, multiply by the weight, sum.

| Factor | Weight | What a high score looks like |
|---|---|---|
| Relevance | 25% | Solves a problem M91 genuinely helps with (human-in-the-loop, approvals, alerting) |
| Intent | 20% | Reader arrives with a concrete problem and can act afterwards |
| Demand | 15% | Real questions people are asking (search, Reddit, HN, SO, GitHub) |
| Competition | 10% | Few good existing answers; low competition or underserved angle |
| Freshness | 15% | Timely (recent change, migration, regulation, product event) |
| Gap | 15% | Not already covered in content_inventory.csv, recent briefs, or Docstar |

**Duplicates score zero.** If the topic or one of its main questions is
already covered, propose an **update brief** for the old post instead of a
new one (see AGENTS.md rule 8).

Rapid-response trend briefs are scored with freshness weighted up; flag them
for closer review. Pinned topics (data/pinned_topics.md) take priority
regardless of score, then rapid-response trends, then the best-scoring topic
respecting topic-group balance.

Record the score and the per-factor breakdown in the brief so a human can
audit the choice.