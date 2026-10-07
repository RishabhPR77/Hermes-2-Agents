# M91 documentation diffs + contradictions

Dated log of contradictions found between doc pages and corrections.
Strategist updates this and flags anything that might affect posts (AGENTS.md
rule 2): when two doc pages contradict each other, avoid the claim and log it
here.

If a decision contradicts a doc, note it with a `(decision overrides)` tag.
Entries usually stay short.

## 2026-10-06 — hedged doc contradiction (seed from Stage 1 research)

- **Contradiction:** `limitations-and-recommendations.md` implies you cannot
  alert an individual; `api.md` + `troubleshoot.md` document the Platform API
  path for direct-to-person alerts (API key → invite recipient via
  `/api/v1/recipients` → alert with body field `phone`).
- **Resolution used:** Platform API supports direct person alerts; keep the
  wording in posts consistent with `api.md` only, skip definitive claims on
  this point.
- **Codified in:** `docs_snapshot.md` (CAN / CANNOT) as of 2026-10-06.

## 2026-10-06 — hedged doc contradiction (seed from Stage 1 research)

- **Contradiction:** the response shape and the polling/close endpoints differ
  between pages: response `id` -> `_id`; polling `GET <link>/alerts/<customId>`
  (playbook) vs `GET /s/<token>/alerts/<id>` (api.md); close `POST <link>/close`
  with `{customId}` vs the m91-skill's `POST /api/v1/alerts/close` with phone +
  customId/alertId.
- **Resolution used:** follow the official `m91-skill` + api.md: `_id`,
  `GET /api/v1/alerts/<customId>?phone=...`, `POST /api/v1/alerts/close`
  (404/403 = success). Avoid numbering claims in posts.

## 2026-10-06 — doc vs model-catalog (non-M91 note)

- Bundled `model-catalog.json` lists `stealth/space-bunny-alpha` under nous,
  but the live Nous Portal 404s it. Hermes-side note, not an M91 doc issue;
  not to be posted.

## 2026-10-06 — snapshot expansion from live docs

- **Change type:** Expansion / clarification (no contradiction).
- **Details:** Live docs (quickstart, fields, api, playbook,
  limitations-and-recommendations) provide richer detail than the seed snapshot.
  Added to CAN: two-credential model (send link + API key), send link GET/POST
  semantics, Platform API endpoints (/recipients, /channels, /alerts), alert
  response shape (decision only from SHARED, note/attachments always present),
  limits (title 5–2000, description 2000, customId 200, 20/6 response options,
  1 MB body, 5s identical-payload window), error envelope with docs URLs,
  delivered/unregistered/noDevice breakdown in send response.
- **Added to CANNOT:** channel/member/link management via API (consent not
  manufacturable), send link rotation (revoke = immediate delete), delivery
  guarantees for misconfigured devices, PERSONAL-only alert close blocked by
  noDevice members, phone call content limitation.
- **Action:** No post changes needed; these are clarifications for future briefs.