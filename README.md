# M91 Blog Agents

Two Hermes agents (Strategist, Writer) plus a decision poller and a weekly
digest produce one blog post every day for **M91**. A reviewer approves each
post on their phone through M91 itself (human-in-the-loop), and approved posts
are published to **Docstar** (M91's blog platform).

## Daily flow (IST)

| Time | Job | What happens |
|---|---|---|
| 07:00 | `m91-strategist` | Reads M91's live docs, reviews the content inventory + Docstar, processes pasted comments, watches trends, researches keywords, scores topics, writes `briefs/YYYY-MM-DD.md`. |
| 08:00 | `m91-writer` | Reads the brief, researches, drafts, humanizes, checks, saves `drafts/YYYY-MM-DD-slug.md`, raises an **M91 approval alert** and posts a readable summary to the reviewer chat. |
| every 10 min | `m91-decision-poller` | `m91_review.py poll` checks for a decision **without waking the AI** unless something changed. Approve → publish. Reject+note → revise once (`-v2`). Deadline passed → reminder + rollover. |
| Mon 09:00 | `m91-weekly` | Digest: comment insights, posts produced/published, review outcomes, M91 docs changes, trends. |

Nothing is published without an explicit **Approve** from M91 (or, only in
fallback mode when M91 reached nobody, an explicit "approve" reply in the
reviewer chat).

## Approving / rejecting on M91

1. Your phone rings with `Blog ready: <title>`.
2. Tap **Approve**, or tap **Reject** and type a reason (a reason is
   required for rejection).
3. The poller notices within ~10 minutes. Approve → package + Docstar (draft
   mode for the first 5 posts) + URL posted to the chat. Reject → one revised
   draft (`-v2`) raises a new alert.

Reminder after 6 hours. **Nothing is published without your approval.**

## Operating the system

All project settings (reviewer names, deadline, severity, publish mode,
Docstar parent ids) live in `config.yaml`. Edit it there, not in code.

- **Change the reviewer / deadline / severity** → edit `config.yaml`:
  `review.primary_reviewer_name`, `review.deadline_hours`, `review.severity`
  (keep MEDIUM; never HIGH/CRITICAL for reviews).
- **Change the reviewer's phone** → edit the Hermes profile `.env`:
  `M91_REVIEWER_PHONE` / `M91_BACKUP_REVIEWER_PHONE`. The new number must
  accept the M91 invite once (rerun `m91_review.py invite` if needed).
- **Add a pinned topic** → append a row to `data/pinned_topics.md`.
- **Add experiences** → append to `data/experience_bank.md` and mark it
  `Approved for public: yes` only if you are happy for it to be published.
  Anything else is used for research only.
- **Paste comments** → append to `data/comments_inbox.md` (channel, post,
  date, text). The Strategist processes new entries the next morning.
- **Switch Docstar draft → publish** → `publish.mode` in `config.yaml`. The
  first 5 posts run in `draft` mode; after you confirm, switch to `publish`.
- **Record a URL manually** → reply `published: <url>` in the reviewer chat
  thread; the Writer records it as `live_url`.
- **Change the AI model** → `hermes model` for chat, `hermes config set
  cron.model <model>` / `cron.model_provider <provider>` for the cron fleet,
  or per job with `hermes cron edit <job> --model <model> --provider <provider>`.
  All skills are provider-neutral.
- **Pause everything** → `hermes pause` (lifts with `hermes resume`), or
  pause individual jobs with `hermes cron edit <job> --paused`.

## Gateway note (read before relying on the schedule)

The Hermes **gateway runs only while you are logged in and the laptop is
awake**. It is installed as a Windows login item, so it starts when you log
in and stops when you log out or shut down. Jobs that miss their window are
**caught up when the gateway comes back** (`cron.catch_up_missed: true` is
on by default) — they are not lost, but they fire late. If that is wrong for
a job, set `cron.catch_up_missed: false` in the injected config
(`C:\Users\risha\AppData\Local\hermes\config.yaml`).

## Scripts

Deterministic Python (no AI), in `scripts/`, installed to
`C:\Users\risha\AppData\Local\hermes\scripts\` (Hermes runs cron scripts only
from there). Credentials come only from environment variables passed through
`terminal.env_passthrough` (see `.env.example`).

| Script | Purpose |
|---|---|
| `m91_review.py` | `raise`, `poll`, `close`, `notify-system`, `invite`, `check` — M91 approval alerts + decision polling (Platform API). |
| `docstar_list.py` | List existing posts under the configured parent (duplicate check, internal links). |
| `docstar_publish.py <draft_path>` | Publish an **explicitly approved** post to Docstar via viaSocket. Refuses without an Approve; idempotent on slug. |

- Dry-run everything first: `M91_DRY_RUN=1` and `DOCSTAR_DRY_RUN=1`.
- Tests: `python scripts/tests/test_m91_review.py` etc.

Reinstall command after any manual edit of the Hermes copy:

```
Copy-Item scripts\*.py C:\Users\risha\AppData\Local\hermes\scripts\
```

## Skills

Sources of truth are `skills/m91-strategist`, `skills/m91-writer`,
`skills/m91-weekly`. They are exposed to Hermes via `skills.external_dirs`
pointing at `D:/1-Academics/Subjects/Walkover/m91-blog/skills`. Hermes can
modify skills over time, so:

- Check for drift: `hermes skills list`.
- Official source: `skills/` in this repo — restore from here if anything
  drifts.

## Fallback and safety

- **No answer is never approval.** A missed 6-hour deadline raises a reminder
  and rolls the item over (max 3 rollovers, then `skipped`). Nothing publishes.
- **M91 unreachable / delivered: 0** → the Writer falls back to asking for
  approval in the chat thread, and `notify-system` pings the reviewer's phone.
- **Docstar unreachable** → status `publish_failed`, package kept in `ready/`,
  reported in chat + `notify-system`.
- **Manual URL fallback** → reply `published: <url>` in the thread.

## No secrets

This repo has zero secrets: only `.env.example` with variable names. Real
values live in `C:\Users\risha\AppData\Local\hermes\.env`.