# Run log

One line per agent run (date, job, outcome, notes). Append only; never edit
older lines. Lines use the format:

```
YYYY-MM-DD | <job/action> | <outcome> | <notes>
```

## 2026-10-06 â€” Setup lines (pre-cron; kept for the record)

2026-10-06 | setup/research | ok | Hermes 0.21.5 capabilities verified; M91 Platform API shapes verified against official m91-skill
2026-10-06 | setup/model | blocked | stealth/space-bunny-alpha removed from Portal (404); z-ai/glm-5.2 needs credits (balance $0) â€” human action logged in SETUP_LOG.md
2026-10-06 | setup/tools | blocked | no web-search backend key configured (Tavily pending); gateway web/dangerous tools unconfigured
2026-10-06 | setup/foundation | ok | Stage 1 files created (AGENTS.md, config.yaml, .env.example, rules/, data/ seeds, README.md, SETUP_LOG.md)
2026-10-06 | setup/foundation-fixes | ok | review applied: daily cadence, decision_log.md, recipient_role column, .env passthrough note, max_revisions: 1
2026-10-06 | setup/skills | ok | m91-strategist/m91-writer/m91-weekly written; hermes config edits A/B/C applied; hermes skills list shows 3 external skills enabled
2026-10-06 | setup/stage3-scripts | ok | scripts/m91_common.py, m91_review.py, docstar_list.py, docstar_publish.py written; scripts/tests: 28 tests pass with mocks; scripts not yet installed into Hermes scripts folder (awaiting approval)
2026-10-06 | setup/stage4-cron | ok | scripts installed to HERMES_HOME/scripts/; config edit D applied (platform_toolsets.cron: [web,file,terminal]); m91_review.py bare = poll for monitor-script; 4 cron jobs created PAUSED (strategist 07:00, writer 08:00, poller 10m, weekly Mon 09:00, all IST); cron doctor clean
2026-10-06 | setup/stage4-verify | ok | monitor gate verified in source (unchanged monitor output suppresses agent run entirely â€” no LLM call; quote in SETUP_LOG.md); Slack deliver commands + config edit E documented in SETUP_LOG.md; waiting on owner setup
2026-10-07 | setup/wake-gate-fix | ok | poller switched from --monitor-script (hash) to --script m91_review.py (content wake gate); scheduler.py:2310/2319 + scheduler_prompt.py:21-35 verified; proof_wake_gate.py dry run shows [0,1,0,0] (real _parse_wake_gate), 28 tests still OK; scripts copy synced; SETUP_LOG.md updated
2026-10-08 | setup/stuck-recovery | ok | decided-but-unactioned rows now re-woken after review.stuck_after_minutes (default 30) up to review.max_stuck_wakes (default 3), then LOW notify-system (customId blog-sys-stuck-<post>-v<ver>) + needs_attention flag; new queue cols stuck_wakes/stuck_last_wake_at/needs_attention in m91_review.py + docstar_publish.py; TestPollStuck 6 new tests, 34/34 pass; proof Scenario B [1,0,1,0,1,0] + 1 LOW notice PASS (proof harness q bug fixed: side_effect re-copied list per call); scripts re-synced; SETUP_LOG.md updated
2026-10-08 | setup/model | ok | free Google-Gemini-OAuth plan ruled out by source (no Google-login flow for AI Studio; free-tier API keys refused, model_setup_flows.py:807-830); chose OpenRouter free instead; OPENROUTER_API_KEY added to hermes .env; test call OK on nvidia/nemotron-3-ultra-550b-a55b:free (z-ai/glm-5.2:free was 404 unavailable-for-free); config edit E APPLIED (cron.model + cron.model_provider: openrouter), config get cron + cron doctor clean; SETUP_LOG.md updated
2026-10-06 | m91-strategist | ok | docs snapshot updated (live docs fetched), 4 trend events logged (2 rapid-response), 15 keywords added, brief written: briefs/2026-10-06.md (rapid-response, Group 1, score 98%), inventory row added, docstar_list failed (missing VIASOCKET_LIST_WEBHOOK)
2026-10-07 | fix/review-alert | ok | alert title 'Blog ready: <short>' (review.alert_title_max 48); description: 'Topic group <n> . <flags> . v<ver> . <n> words' + single drafts/ path + 'Reminder after 6 hours'; common.body_word_count + 'm91_review.py wordcount' command + Writer OVER-trim before save; review budgets (strategist <=14 / writer <=10 model calls); 429 -> [CRON_FAILURE] + LOW notify-system (rule 10) + poller usage-audit watchdog (cron_429_window_minutes 20); 49/49 tests + wake-gate proof A/B PASS; scripts re-synced; M91_API_KEY added to hermes .env (owner-provided); NO alerts sent; jobs remain PAUSED
2026-10-07 | setup/slack-delivery | ok | gateway = Windows login item (Startup Hermes_Gateway.vbs -> gateway-service vbs -> python -m hermes_cli.main gateway run; no Windows service, relaunch-at-login verified); bot added to home channel C0C74JB08AF (owner); all 4 cron jobs switched --deliver slack, still PAUSED; test message sent via 'hermes send -t slack' exit 0 (first attempt not_in_channel before bot was added)
2026-10-07 | setup/m91-invites | ok | reviewer phones uncommented in hermes .env (both ACTIVE); invited main + backup via m91_review.py invite main/backup (exit 0, state pending, labels 'Primary reviewer'/'Backup reviewer'); NO review alerts sent; awaiting acceptance then state=accepted+reachable check
2026-10-07 | setup/m91-invites | ok | both reviewers ACCEPTED + reachable=True (invite main/backup re-query: 'invited and accepted'); +91 E.164 attempt rejected by API (VALIDATION_ERROR: digits only, e.g. 919876543210) so phones stay bare 91xxxxxxxxxx in .env; NO review alerts sent; cron jobs remain PAUSED
2026-10-07 | fix/live-decision-read | ok | LIVE BUG: poll got 404 reading decisions by customId; M91 alert endpoint resolves by Mongo _id. Fixed read_decision + row_alert_ids/append_row_alert chain columns (alert_ids added to QUEUE_COLS), raise/reminder/rollover alerts now carry customId so close-by-customId matches; tests 50/50; refixed live poll returned decision=Approve wakeAgent true, close 1 1 exit 0; inventory back to brief; NO docstar publish (test); sync to HERMES_HOME
