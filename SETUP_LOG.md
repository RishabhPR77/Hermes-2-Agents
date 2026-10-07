# SETUP_LOG.md

Every command run, every file created, and what still needs doing. No secrets
are ever recorded here.

Date convention: `2026-10-06` = today.

---

## 2026-10-06 — Research (Stage 1) and decisions

Verified with live help/docs: `hermes --help`, `hermes cron create --help`,
`hermes tools --help`, `hermes skills --help`, `hermes status`, `hermes config
show`, M91's docs (llms.txt index: quickstart, fields, api, playbook,
troubleshoot, limitations), Hermes cron docs, and the official
`msg91/m91-skill` repo (SKILL.md + `scripts/m91.sh`, which show the exact
Platform API request shapes).

### Key findings

- **Hermes** v0.21.5 (install `C:\Users\risha\AppData\Local\hermes`). Gateway
  installed as a Windows login item; runs only while logged in and the laptop
  is awake (README note added). No messaging platform configured yet (Slack
  pending).
- **M91 Platform API** (`Bearer m91sk_…`) supports direct alerting of one
  person: invite via `POST /api/v1/recipients` (phone, label), person must
  accept in the M91 app (`reachable: false` until then), then
  `POST /api/v1/alerts` with body field **`phone`** plus the normal alert
  fields; decision read via `GET /api/v1/alerts/<customId>?phone=…`; close a
  person alert via `POST /api/v1/alerts/close` with the same phone + customId
  (404/403 = nothing to close = success). `delivered: 0` is a failure;
  `deduplicated: true` is not. No server-side expiry; we own the deadline.
  `decision` is set ONLY by a `SHARED` response.
- **Model problem (found during research):** the configured
  `stealth/space-bunny-alpha` 404s on Nous Portal (removed), and the account
  has $0 credits so paid models are unavailable. **HUMAN ACTION:** add credits
  at portal.nousresearch.com/billing; then pin `cron.model = z-ai/glm-5.2`,
  `cron.model_provider = nous`.
- **Web search:** unused backend (portal Tool Gateway shows "Web tools: not
  configured") and no search key in `.env`. **HUMAN ACTION:** add a Tavily key
  via `hermes tools`.
- **Docstar:** user chose **viaSocket's Docstar integration** (Create Page,
  List All Pages, Find Documents, View Page Text and Metadata). Two webhook
  flows (publish, list); both check `X-ViaSocket-Secret`.

### Decisions (user)

1. M91 alerting = **Platform API direct alerts** (API key), not send links.
2. Docstar access = **viaSocket** webhook-triggered flows.
3. Reviewer chat = **Slack** (setup pending, user side).
4. Skills installed via `skills.external_dirs` → this repo's `skills/` dir.
5. Secrets are entered by the owner directly into
   `C:\Users\risha\AppData\Local\hermes\.env`; never pasted in chat.
6. Web search via **Tavily** key (owner enters it).
7. Cron model = **z-ai/glm-5.2** on **nous** (after credits are added).
8. Cron jobs restricted to toolsets **web, file, terminal**.
9. Review flow = **primary reviewer only**; backup reviewer only after the
   6-hour deadline with no decision (together with the reminder). First
   SHARED decision wins; sibling alert closed; later conflicts logged.
10. `notify-system` = LOW severity to the **primary reviewer's phone**; no
    separate system channel for now.
11. Config edits approved in principle (shown before applying in Stage 3/5):
    A `skills.external_dirs`, B `terminal.env_passthrough`
    [M91_API_KEY, M91_REVIEWER_PHONE, M91_BACKUP_REVIEWER_PHONE,
    VIASOCKET_PUBLISH_WEBHOOK, VIASOCKET_LIST_WEBHOOK, VIASOCKET_SHARED_SECRET],
    D `platform_toolsets.cron: [web, file, terminal]`,
    C `cron.mirror_delivery: true`; E `cron.model`/`cron.model_provider`
    (applied only after credits confirmed).

### Commands run (all verified read-only during research)

- `hermes --help`, `hermes cron create --help`, `hermes skills --help`,
  `hermes tools --help`, `hermes tools list`, `hermes status`,
  `hermes config show`, `hermes portal info`, `hermes cron --help`.
- `hermes skills inspect skills-sh/msg91/m91-skill/m91-alerting` (official M91
  skill; clean, install pending Stage 3).
- Model probes (all failed, logged as findings above):
  `hermes -z "…" -m stealth/space-bunny-alpha --provider nous` (404),
  `-m nousresearch/hermes-4` (404), `-m z-ai/glm-5.2` (no credits).

## 2026-10-06 — Foundation (Stage 1)

Files created:

- Folder tree per brief §3 (skills/, scripts/, scripts/tests/, rules/, data/,
  briefs/, drafts/, ready/).
- `AGENTS.md` — rulebook for every cron run.
- `config.yaml` — project settings (no secrets).
- `.env.example` — secret VARIABLE NAMES only (values go in the Hermes .env).
- `README.md` — flow + how to operate + gateway-only-on-login note.
- `SETUP_LOG.md` — this file.
- `rules/` — style_guide.md, banned_phrases.md, topic_groups.md, scoring.md.
- `data/` — CSV headers + Markdown seeds (incl. docs_snapshot.md,
  docs_changes.md).

Stage 1 approved after review fixes:

- `AGENTS.md` rule 1: one post **every day** (jobs run daily).
- `AGENTS.md` rule 4: conflicting/late SHARED decisions → new
  `data/decision_log.md` (docs_changes.md stays M91-docs-only).
- `data/review_queue.csv` gained a `recipient_role` column (`main`/`backup`;
  no phone numbers in the file). New header:
  `item_id,post_id,version,type,alert_id,custom_id,recipient_role,sent_at,deadline,decision,note,decided_by,decided_at,reminders,rollovers,status`
- `.env.example` now points to the Hermes config for `terminal.env_passthrough`.
- `config.yaml` added `review.max_revisions: 1` (skills read it).

## 2026-10-06 — Skills (Stage 2)

- Wrote `skills/m91-strategist/SKILL.md`, `skills/m91-writer/SKILL.md`,
  `skills/m91-weekly/SKILL.md` (source of truth; Hermes reads them via
  `skills.external_dirs`).
- Applied Hermes config edits (diffs shown to owner first):
  - **A** `skills.external_dirs: ["D:/1-Academics/Subjects/Walkover/m91-blog/skills"]`
  - **B** `terminal.env_passthrough: [M91_API_KEY, M91_REVIEWER_PHONE,
    M91_BACKUP_REVIEWER_PHONE, VIASOCKET_PUBLISH_WEBHOOK,
    VIASOCKET_LIST_WEBHOOK, VIASOCKET_SHARED_SECRET]` (verified the key lives
    at `terminal.env_passthrough` in Hermes source `tools/env_passthrough.py`;
    `cron` scripts read it this way)
  - **C** `cron.mirror_delivery: true` (key verified in Hermes source
    `config_defaults.py` + `cron/scheduler_delivery.py`; mirrors cron
    deliveries into the session)
- Verified: `hermes skills list` shows `m91-strategist`, `m91-writer`,
  `m91-weekly` as `external` / `local` / `enabled`.
- Official `skills-sh/msg91/m91-skill/m91-alerting` reference: inspected
  during research; not installed — our own scripts remain the only path for
  approvals/publishing (brief §8).

## 2026-10-06 — Deterministic scripts (Stage 3, files only; NOT installed)

- `scripts/m91_common.py` — shared stdlib-only helpers: secret registration +
  redaction, env loading, `M91_BLOG_ROOT` project discovery, config load
  (PyYAML with mini-YAML fallback), CSV read/write (header preserved), time +
  deadline helpers, `http_request` (returns `(status, envelope)`,
  `NetworkError`/`ApiError`), envelope `data_of`/`error_of`, front-matter
  split, word count, minimal `markdown_to_html`. Exit-code table:
  `0 ok · 1 usage/not-found · 2 API/network · 3 delivered 0 · 4 env · 5 poll
  all failed · 6 viaSocket/Docstar · 7 unapproved · 8 duplicate slug ·
  9 already published`.
- `scripts/m91_review.py` — `raise <post_id> <version>` (main only, opens a
  queue row, inventory → `awaiting_review`), `poll` (reads decisions on
  base + `-r<n>` candidates, records approve/reject, closes sibling +
  reminders, skips past `max_revisions`/`max_rollovers`, escalated deadline →
  backup reviewer with new deadline then reminders, prints the `wakeAgent`
  gate JSON as the LAST stdout line), `close <post_id> <version>` (both
  roles' candidates; 404/403 = success), `notify-system <msg>` (LOW,
  auto-close, deduped `blog-sys-…` id), `invite <main|backup>`, `check`.
- `scripts/docstar_list.py` — calls the viaSocket list flow; prints
  `<slug> | <title> | <url> | <updated>`.
- `scripts/docstar_publish.py` — enforces refusals before any webhook call:
  unapproved → exit 7, duplicate slug on Docstar → exit 8, already published
  → exit 9; builds `create` payload (mode draft, markdown + HTML, meta, tags,
  schema), updates `content_inventory.csv` + `review_queue.csv`, writes
  `ready/<date>-<slug>/post.md`.
- `scripts/tests/` — `fixtures.py` + `test_m91_review.py` +
  `test_docstar_publish.py`; **28 unit tests, all passing** with mocked HTTP:
  approve; reject with note; second rejection → skipped; deadline → backup +
  reminder; rollover limit → skipped; free-text answer is not a decision;
  zero delivered → exit 3; duplicate decision event idempotent; conflicting
  late decision logged + ignored; M91 unreachable → exit 5; unapproved / dup
  slug / already-published refusals; secrets never printed.
- Dry runs: `M91_DRY_RUN=1` (m91_review), `DOCSTAR_DRY_RUN=1`
  (docstar: checks refusals 7/8/9, prints payload, never POSTs).
- Ran: `python scripts/m91_review.py poll` on real data → `{"wakeAgent":
  false}`, exit 0 (no side effects). `notify-system`/list without env → exit 4
  (by design).
- NOT installed into `C:\Users\risha\AppData\Local\hermes\scripts\` — Stage 3
  approval pending (rule: show → approve → then wire cron).

## 2026-10-06 — Cron wiring (Stage 4)

- **Installed** the four scripts into `C:\Users\risha\AppData\Local\hermes\scripts\`
  (= `HERMES_HOME/scripts/`, verified against Hermes source
  `cron/scheduler_script.py`: scripts must resolve inside that dir). Python
  resolves `import m91_common` from the same dir.
- **Config edit D applied** (diff shown to owner first):
  `platform_toolsets.cron: [web, file, terminal]` — verified the key name in
  Hermes source (`cron/scheduler.py` + `hermes_cli/config.py`). `hermes cron
  doctor` clean.
- `m91_review.py` now defaults to `poll` with no arguments (cron `--script`
  takes a bare path, no argv). Poll always prints a single-line wake gate JSON
  as its **last stdout line** (`{"wakeAgent": false}` when idle, true + context
  on any new decision / deadline event). See the wake-gate section below for
  why the gate is content-based, not hash-based.
- Created four cron jobs, **all PAUSED** (`hermes cron list` shows
  `[paused]`, `Deliver: local` until Slack is configured):
  - `443ddc3e2658` m91 strategist — `0 7 * * *` (07:00 IST) — skill m91-strategist
  - `6a8cb5c2894f` m91 writer — `0 8 * * *` (08:00 IST) — skill m91-writer
  - `54e19d7cb428` m91 decision poller — `10m` — pre-run script `m91_review.py` (wake gate)
  - `42c02cba44cb` m91 weekly digest — `0 9 * * 1` (Mon 09:00 IST) — skill m91-weekly
- System timezone is IST (UTC+05:30), so `0 7 * * *` fires 07:00 local = IST.

## 2026-10-06 — Stage 4 follow-up checks (owner verified)

### 1. Poller wake gate is content-based (`--script`), NOT hash-based (source-verified)

The decision poller runs `--script m91_review.py` (bare = `poll`) as a **pre-run
wake gate** — this supersedes the earlier `--monitor-script` design (see the
2026-10-07 entry below). Hermes evaluates the poll's **last stdout line**: if it
is JSON `{"wakeAgent": false}` the agent is skipped entirely — **no LLM call, no
delivery**:

- `cron/scheduler_prompt.py:21-35` — the gate:
  ```
  def _parse_wake_gate(script_output: str) -> bool:
      """Wake gate: False only if the last non-empty stdout line is JSON
      ``{"wakeAgent": false}`` (agent skipped entirely — no LLM run, no delivery);
      anything else wakes normally. ..."""`
  ```
- `cron/scheduler.py:2293-2319` — the pre-run gate in the agent-backed path:
  ```
  # Wake-gate: run the pre-check script BEFORE building the prompt ...
  prerun_script = _run_job_script_with_claim_heartbeat(...)
  _ran_ok, _script_output = prerun_script
  if _ran_ok and not _parse_wake_gate(_script_output):
      logger.info("Job '%s' (ID: %s): wakeAgent=false, skipping agent run", ...)
      note_cron_skipped(job)
      ...
      return (True, silent_doc, SILENT_MARKER, None), None
  ```
- When the gate wakes (true), that same script output is injected into the
  assembled prompt, so the agent sees the poll lines + the gate JSON context.

Note: the gate is **content-based** (per-line), so an `event → idle` transition
cannot cause a second wake — unlike `--monitor-script`, whose hash compares bytes
against the previous run. The agent also runs exactly when a decision/deadline
event is emitted; there is no first-run baseline wake.

### 2. Prepared: switching deliveries from `local` to Slack

Prerequisites (owner): `hermes gateway setup` → Slack (Socket Mode); put the
reviewer chat channel id in `C:\Users\risha\AppData\Local\hermes\.env` as
`SLACK_HOME_CHANNEL=C<channel-id>` (or use the explicit form below). Then run:

```powershell
hermes cron edit 443ddc3e2658 --deliver slack
hermes cron edit 6a8cb5c2894f --deliver slack
hermes cron edit 54e19d7cb428 --deliver slack
hermes cron edit 42c02cba44cb --deliver slack
hermes cron list   # verify each job shows "Deliver: slack"
```

Bare `slack` = the configured Slack home channel (source-verified:
`scheduler_delivery.py:688-689` uses `_get_home_target_chat_id("slack")` from
`SLACK_HOME_CHANNEL`; bare-platform token = deliberate home-channel address).
Explicit alternative: `hermes cron edit <id> --deliver slack:<chat_id>`
(grammar `platform:chat_id`, `scheduler_delivery.py:645-672`).

### 3. Prepared then APPLIED: config edit E (cron.model) — 2026-10-08

Planned for Nous (z-ai/glm-5.2), but re-decided: the user wanted a free model
with a Google login and asked Hermes to support Google Gemini free OAuth.
**Hermes has no Google-login flow for Gemini** (Google AI Studio = API key
only, and the code actively refuses free-tier keys — free tier is ≤250 RPD for
flash and exhausted in a few agent turns; `model_setup_flows.py:807-830`).
Vertex AI is OAuth2 but needs a billing-enabled GCP project. So the free path
chosen was **OpenRouter `:free` SKUs** (Google sign-in OK at openrouter.ai, no
card, zero-priced models; API-key auth so there is no token to refresh for
unattended cron runs).

Applied to `C:\Users\risha\AppData\Local\hermes\config.yaml` `cron:` block:

```yaml
cron:
  catch_up_missed: true  # False skips past-grace recurring misses after planned downtime.
  mirror_delivery: true  # Approved edit C: mirror cron job deliveries into the session.
  model: nvidia/nemotron-3-ultra-550b-a55b:free  # Approved 2026-10-08 (edit E): free OpenRouter model, no credits.
  model_provider: openrouter
```

Why this slug and not `z-ai/glm-5.2:free`: the live `:free` availability
changes — `z-ai/glm-5.2:free` 404'd ("unavailable for free") during the test.
I queried OpenRouter for currently zero-priced models and picked the largest
tool-capable slug also listed in Hermes' catalog. Test call
(`hermes -z "Reply with exactly: OK" -m nvidia/nemotron-3-ultra-550b-a55b:free
--provider openrouter`) returned `OK`. If it later 404s, re-run that probe and
swap the slug.

No job carries a `--model` pin, so all four follow `cron.model` (source
`cron/scheduler.py` `_load_cron_job_config`: per-job pin > cron.model > main
agent model). Verified after applying: `hermes config get cron` shows
`model:` + `model_provider:` above, `hermes cron doctor` clean.

## 2026-10-07 — Poller switched from `--monitor-script` to the `--script` wake gate

**Problem found:** `--monitor-script` is **hash-based**; a run only measures
whether stdout bytes changed vs the previous run. After a decision event wakes
the agent (`{"wakeAgent": true, ...}`), the *next* idle tick prints
`{"wakeAgent": false}` again, the bytes differ → the agent would wake a second
time for nothing. A monitor hash is a transition detector, not a
`wakeAgent: false` gate.

**Fix:** `--script` evaluates the poll's **last stdout line** as a
content-based gate. `{"wakeAgent": false}` always skips the agent (no LLM call),
so an `event → idle` transition cannot re-wake. Verified in installed Hermes
source: `cron/scheduler_prompt.py:21-35` (`_parse_wake_gate`) and
`cron/scheduler.py:2293-2319` (agent-backed pre-run wake gate, returns
`SILENT_MARKER` when gated).

**Applied:** `hermes cron edit 54e19d7cb428 --monitor-script= --script m91_review.py`
→ job now shows `Script: m91_review.py`, no `Monitor`; `hermes cron doctor` clean.

**Dry-run proof** (`scripts/tests/proof_wake_gate.py` — real
`_parse_wake_gate` from the installed hermes-agent + real `poll` stdout, M91 API
mocked). Four consecutive ticks:

```
poll tick                last stdout line (gate)                  Hermes    agent run
1 idle (nothing new)     {"wakeAgent": false}                     False     no
2 decision event         {"wakeAgent": true, "context": {"items": True      yes
3 idle (post-event)      {"wakeAgent": false}                     False     no
4 idle (stable)          {"wakeAgent": false}                     False     no
wake vector (agent runs per tick): [0, 1, 0, 0]   expected: [0, 1, 0, 0]
queue state after: decision='Approve' decided_by='main' status='open'
```

`m91_review.py poll` needs no code change for this — it already prints the gate
JSON as its last stdout line.

## 2026-10-07 — Stuck-item recovery added to the poller

A row with a recorded reviewer decision (`Approve`/`Reject`) but still
`status=open` means the agent woke for the decision but failed to finish
(Docstar down, model error, etc.). The poller now recovers:

- **Grace:** a decided row is left alone for `review.stuck_after_minutes`
  (default `30`, minutes since `decided_at` or since the last stuck re-wake).
- **Re-wake:** past the grace it is re-woken (gate `{"wakeAgent": true}` with
  `decision: "stuck"`, `stuck_wake: n`, `original_decision`) up to
  `review.max_stuck_wakes` (default `3`) times. Grace restarts from each wake,
  so attempts are ≥30 min apart.
- **Escalate:** after 3 re-wakes it sends a **LOW** `notify-system` notice to
  the primary reviewer (dedup customId `blog-sys-stuck-<post>-v<ver>`), sets
  the row flag `needs_attention` and **stops waking** — it is now a human
  problem, not an agent one.
- New queue columns: `stuck_wakes`, `stuck_last_wake_at`, `needs_attention`
  (added to both `m91_review.py` and `docstar_publish.py` `QUEUE_COLS`).

**Dry-run proof** now includes Scenario B (stuck re-wakes then notice):

```
poll tick                  last stdout line                       Hermes  agent   note
1 decision, un-actioned 40m {"wakeAgent": true, ...}              True    yes     stuck wake 1 of 3
2 10m later (grace)        {"wakeAgent": false}                   False   no      inside 30m grace
3 35m after wake 1         {"wakeAgent": true, ...}              True    yes     stuck wake 2 of 3
4 10m later (grace)        {"wakeAgent": false}                   False   no      inside 30m grace
5 40m after wake 2         {"wakeAgent": true, ...}              True    yes     stuck wake 3 of 3
6 40m after wake 3         {"wakeAgent": false}                   False   no      LOW notice sent, needs_attention
wake vector: [1, 0, 1, 0, 1, 0]  expected  -> OK
queue state: decision='Approve' stuck_wakes=3 needs_attention='yes' status='open'
stuck LOW notices POSTed: 1 (flag set: True)
```

Unit tests: `TestPollStuck` (6 cases — grace, re-wake count, increments,
exhaust→notice+flag, LOW payload/dedup id, no repeat after `needs_attention`).
Full suite 34/34 pass. Scripts re-synced to `HERMES_HOME/scripts/`.

## Still needed (owner — most before Stage 6)

- [x] ~~Add Nous Portal credits → then I pin `cron.model = z-ai/glm-5.2`.~~ Done
  2026-10-08 via **OpenRouter free** instead (`nvidia/nemotron-3-ultra-550b-a55b:free`,
  provider `openrouter`); the OpenRouter API key is already in the Hermes `.env`.
- [x] ~~Add a **Tavily** API key via `hermes tools`~~ — done keyless: web search +
  extract already enabled in the Hermes toolsets (verified with a live search).
- [x] ~~`hermes gateway setup` → Slack (Socket Mode)~~ — done 2026-10-07:
  gateway runs as a Windows **login item** (Startup `Hermes_Gateway.vbs` →
  `gateway-service/Hermes_Gateway.vbs` → `python -m hermes_cli.main gateway
  run`; no Windows service). Bot added to home channel `C0C74JB08AF`
  (owner-added 2026-10-07); login-item relaunch verified for logout/login.
- [x] ~~Switch cron deliveries to Slack~~ — done 2026-10-07:
  `hermes cron edit <id> --deliver slack` for all four jobs
  (`443ddc3e2658`, `6a8cb5c2894f`, `54e19d7cb428`, `42c02cba44cb`);
  `cron list` shows `Deliver: slack` on each, all still **PAUSED**.
- [x] ~~Test message to the Slack home channel~~ — done 2026-10-07:
  `hermes send -t slack …` exit 0 (first attempt failed
  `Slack API error: not_in_channel` until the bot was added to the channel).
- [x] ~~M91 API key~~ — `M91_API_KEY` placed in `C:\Users\risha\AppData\Local\hermes\.env`
  (owner-provided 2026-10-07). **No alert has been sent** — raises/notifications
  stay quiet until the owner asks for a live test.
- [ ] Add to `C:\Users\risha\AppData\Local\hermes\.env`:
  `M91_REVIEWER_PHONE`, `M91_BACKUP_REVIEWER_PHONE`,
  `VIASOCKET_PUBLISH_WEBHOOK`, `VIASOCKET_LIST_WEBHOOK`, `VIASOCKET_SHARED_SECRET`.
- [ ] Both reviewers install M91, sign in, accept the invite, send a test
  alert (verify the phone actually rings).
- [ ] viaSocket: create + publish two flows (Docstar **Create Page** under the
  blog parent; Docstar **List All Pages**/**Find Documents**), each checking
  `X-ViaSocket-Secret`, and give me the two webhook URLs (add to above .env).
- [ ] Docstar parent page ids → I fill `publish.blog_parent_page` and
  `publish.test_parent_page` in `config.yaml`.
- [ ] Confirm the two reviewer names in `config.yaml`.

## 2026-10-07 — Review-alert polish + rate-limit watchdog (fixes 1–6)

Applied the six fixes requested by the owner (`config.yaml`,
`scripts/m91_common.py`, `scripts/m91_review.py`, `skills/m91-writer`,
`skills/m91-strategist`, `AGENTS.md`, tests):

1. **Alert title** → `Blog ready: <short title>`: full title truncated at a
   word boundary to `review.alert_title_max` (48) with `…`, prefix from
   `review.alert_title_prefix` (`config.yaml`).
2. **Description** → one readable meta line
   `Topic group <n> · <flags> · v<ver> · <n> words`, a single `drafts/`
   prefix (`common.draft_rel` — also fixes the stuck-notice), whole-hours
   reminder (`common.format_hours` → "Reminder after 6 hours", no `6.0`).
3. **Word count** → shared `common.body_word_count` (excludes front matter +
   the trailing "Check results" section); new `m91_review.py wordcount
   <draft>` prints `wordcount:/target:/status:`; Writer **trims OVER drafts
   before saving** (skill 1.7); the alert description gains a word-count
   warning when the draft is outside `topics.target_words`.
4. **Efficiency** → per-run model-request budgets in the skills
   (Strategist ≤ 14, Writer ≤ 10): batch file reads into one message, cap web
   searches (2–3 / 1–2), write once + one edit pass. Expected daily content
   usage ≈ 22–28 requests — under the OpenRouter free ~50/day; exact per-key
   totals are visible on the OpenRouter usage page.
5. **429 → never silent** → AGENTS.md rule 10 + both skills: on HTTP 429 /
   quota error run `notify-system "<reason>"` (LOW), reply
   `[CRON_FAILURE]`, stop. Backstop: the poller watchdog
   `_notify_cron_429s` reads `HERMES_HOME/cron/usage_audit.jsonl` every poll
   and sends one LOW auto-closed notice per failed attempt within
   `review.cron_429_window_minutes` (20), deduped via
   `data/cron_429_sent.json`; if M91 env isn't set it records the gap instead
   of crashing. Installed poller still boots to `{"wakeAgent": false}`.
6. **Tests** → `TestAlertFormat`, `TestBodyWordCount`, `TestWordcountCommand`,
   `TestCron429Watchdog`; full suite **49/49 PASS**; wake-gate proof
   scenarios A/B PASS; scripts re-synced byte-identical to
   `HERMES_HOME/scripts/`; all four cron jobs remain **PAUSED** (none sent an
   alert).