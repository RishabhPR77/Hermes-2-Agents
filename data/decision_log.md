# Decision log

Conflicting or late `SHARED` decisions, and any decision handling worth
revisiting. `data/docs_changes.md` is only for M91 documentation changes;
this file is only for decisions. Append one entry per event with a date.

## Format

```
## YYYY-MM-DD — <post id / custom id> — <type>

- **Type:** conflicting-reply | decided-once | ignored | other
- **What happened:** who replied what, when, and why it was overruled
- **Action taken:** e.g. "ignored; first SHARED Approve by <decider> already
  recorded", "sibling alert closed", "logged for review"
```

Rule this file exists to serve (AGENTS.md rule 4): the first SHARED decision
wins; later or conflicting SHARED replies are ignored and logged here, and
the sibling reviewer's alert is closed. No entry yet — the first one will be
recorded the first time a conflicting or late decision arrives.## 2026-10-07 - 1 (v1) - LIVE TEST approve (item 9d858a53c97f)

- **Type:** approve
- **What happened:** owner tapped Approve in the M91 app on test alert blog-2026-10-06-ai-agent-spends-160-domain-human-approval-v1 (id 6ac5d29d5c5e59d9a69e7d4f); poll recovered it by alert _id after the customId-lookup bug was fixed.
- **Action taken:** decision recorded (decided_by=main); no Docstar publish (test draft, publish.mode=draft, viaSocket not configured); queue row closed after test.
