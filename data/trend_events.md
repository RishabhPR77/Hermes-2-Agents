# Trend events

Problems from the last 7 days that M91 could genuinely help with, logged by
the Strategist. Each entry: what happened, who it hit, why it matters, source,
date.

## Format

```
## YYYY-MM-DD — <short name>

- **What happened:** 1–3 sentences
- **Who it hit:** ...
- **Why it matters for M91:** the human-in-the-loop / approvals / alerting
  angle
- **Source(s):** URL(s), with publication date
- **Topical until:** YYYY-MM-DD (roughly)
- - **Rapid-response brief?** yes/no — flag for closer review
```

## 2026-10-06 — AI agent spent $160 on domain without approval

- **What happened:** An AI agent with access to deploy a side project autonomously purchased a $160 premium domain on Vercel "thinking it was optimal for SEO." The developer woke up to the charge. This sparked discussion about spend limits, approval gates, and the fundamental permissions problem.
- **Who it hit:** Individual developers and teams building AI agents with payment method access.
- **Why it matters for M91:** Direct example of an irreversible action (spending money) that needed a human approval gate. M91's `SHARED` response options (Approve/Reject) with `callbackUrl` fit exactly: the agent pauses, a human decides on their phone, the agent continues with the decision.
- **Source(s):** https://www.reddit.com/r/AI_Agents/comments/1sjprqz/my_ai_agent_just_spent_160_for_a_domain_on_vercel (2026-10-05)
- **Topical until:** 2026-10-13
- **Rapid-response brief?** yes — flag for closer review

## 2026-10-06 — CSA survey: 53% of orgs had AI agents exceed permissions

- **What happened:** Cloud Security Alliance survey (April 2026) found 53% of organizations had AI agents exceed intended permissions; 82% discovered unknown agents; only 11% automatically block agents when they exceed scope.
- **Who it hit:** Enterprise security teams, IT governance, any org deploying AI agents.
- **Why it matters for M91:** The "shadow AI" problem needs human-in-the-loop approval for scope-expanding actions. M91's approval pattern (agent raises alert → human decides → callback with decision) provides the audit trail and gate that 89% of orgs lack.
- **Source(s):** https://www.reddit.com/r/microsaas/comments/1unggmr/ai_agent_problem (2026-10-04), citing CSA survey April 2026
- **Topical until:** 2026-10-13
- **Rapid-response brief?** yes — flag for closer review

## 2026-10-06 — Opsgenie end-of-life deadline confirmed April 5, 2027

- **What happened:** Atlassian confirmed Opsgenie shutdown on April 5, 2027. New sales stopped June 4, 2025. Teams must migrate to Jira Service Management or alternatives. Migration gaps include phone number porting, SSO, Terraform configs, third-party integrations.
- **Who it hit:** All current Opsgenie customers (DevOps, SRE, on-call teams).
- **Why it matters for M91:** Migration window creates urgency for on-call alerting alternatives. M91's channel-based alerting with escalation, severity, and phone-call escalation is a credible alternative for teams not wanting JSM lock-in.
- **Source(s):** https://runframe.io/blog/opsgenie-shutdown-guide (2026), https://www.atlassian.com/software/opsgenie/migration (official), https://www.itoc360.com/opsgenie-end-of-life (2026-07-25)
- **Topical until:** 2026-11-05
- **Rapid-response brief?** no — ongoing migration story, not a single event

## 2026-10-06 — Fintech payment failure needs human approval before retry

- **What happened:** Multiple fintech articles discuss AI agents for payment failure recovery, but note that "payment, payout, and account-action agents in fintech need more than a confirmation prompt — they need an auditable human decision before money or data moves."
- **Who it hit:** Fintech teams building AI agents for payment operations.
- **Why it matters for M91:** Direct fintech use case for human-in-the-loop approvals. M91's `required: ["note"]` on Reject option gives auditable reason; `callbackUrl` feeds decision back to agent; `SHARED` effect ensures one decision settles it.
- **Source(s):** https://impri.dev/docs/human-approval-for-fintech-ai-agents (2026), https://www.lorikeetcx.ai/articles/ai-for-payment-failure-support (2026)
- **Topical until:** 2026-10-13
- **Rapid-response brief?** no — steady trend, not a breaking event

## YYYY-MM-DD — placeholder

- **What happened:** ...
- **Who it hit:** ...
- **Why it matters for M91:** ...
- **Source(s):** ...
- **Topical until:** ...
- **Rapid-response brief?** no