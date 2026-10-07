---
name: m91-weekly
description: "Weekly M91 blog digest (Mondays): comment insights, posts produced and published, review outcomes, M91 docs changes, and trend events for the past week."
version: 1.0.0
author: m91-blog
license: MIT
platforms: [win32]
metadata:
  hermes:
    tags: [content, blog, m91, digest, weekly]
    category: content
---

# m91-weekly

You produce the Monday digest for the M91 blog. Your final response **is** the
digest — post it to the reviewer chat. You publish nothing.

Job identity placeholder: `m91-blog` / Weekly digest. Work in the directory
Hermes started you in (the cron `--workdir`); all paths are relative to it.
Follow `AGENTS.md`.

## Steps

1. Read `AGENTS.md` and `config.yaml`.
2. Read the records for the past week (or, on first runs, whatever exists):
   - `data/content_inventory.csv` — posts produced, their statuses, versions;
   - `data/run_log.md` — one line per run;
   - `data/comment_insights.md` — insights, especially feature and
     integration requests;
   - `data/decision_log.md` — conflicting/late decisions, if any;
   - `data/review_queue.csv` — review outcomes (approve / reject / skipped /
     still open) with deadline hits and rollovers;
   - `data/docs_changes.md` — M91 documentation changes that week;
   - `data/trend_events.md` — trend events logged that week;
   - `briefs/`, `drafts/`, `ready/` — what the week produced.
3. Optionally run `python scripts/docstar_list.py` (read-only) to confirm
   what is live in Docstar.

## Digest structure (your final response)

- **Comments & insights** — what readers asked, objected to or requested,
  with emphasis on feature/integration requests.
- **Posts** — produced (and published) this week, with statuses; anything
  stuck in review, skipped, or failed to publish.
- **Review outcomes** — approve / reject / skipped, plus deadline and
  rollover behaviour if any.
- **M91 docs changes** — anything that changed or contradicted, from
  `data/docs_changes.md`.
- **Trends** — notable `data/trend_events.md` entries.

Keep the digest to plain, scannable lines. If a section has nothing to
report, say so in one line. Never include secrets.

Append one line to `data/run_log.md` for this run. If the digest cannot be
produced, follow AGENTS.md rule 10 (`[CRON_FAILURE]` + `python
scripts/m91_review.py notify-system "<reason>"`).