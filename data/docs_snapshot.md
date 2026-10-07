# M91 docs snapshot — 2026-10-06

Source of truth: the M91 site and docs live at
https://m91-site.embarko.app/ and https://siren-backend-1091285226236.asia-south1.run.app/llms.txt
(index → quickstart.md, fields.md, api.md, playbook.md, troubleshoot.md,
limitations-and-recommendations.md).

## M91 CAN (as of this snapshot; re-verify each run)

- Raise an alert that interrupts every phone in a **channel** at full volume,
  through silent mode and Do Not Disturb, re-ringing until somebody answers,
  escalating to a phone call only for HIGH/CRITICAL and only under documented
  conditions.
- Alert **directly to one person**: Platform API key (`m91sk_…`,
  `Authorization: Bearer *** `POST /api/v1/recipients` to invite a phone
  number → person accepts in the M91 app → `POST /api/v1/alerts` (body field
  `phone` + the normal alert fields) → decision read via
  `GET /api/v1/alerts/<customId>?phone=…` → close via
  `POST /api/v1/alerts/close` with the same phone + customId/alertId.
- Create channels via the API key (`POST /api/v1/channels`, returns a
  `sendLink`); alerting a channel is done with that send link, not the key.
- `responseOptions`: up to 20 by POST, 6 by send-link form; `SHARED` and
  `PERSONAL` effects; `required: ["note"]` / `optional` per option; `other`
  defaults true (free text, always `PERSONAL`).
- `severity`: LOW / MEDIUM / HIGH / CRITICAL. MEDIUM (default) re-rings for
  ~2 minutes and **never phones**. Only CRITICAL always phones; HIGH phones
  only if nobody has responded AND nobody has opened the alert.
- `customId`: while an alert with that id is open, re-sending it alerts
  nobody and returns the existing alert (`deduplicated: true`); after close,
  re-sending reopens the same record (`reopenCount`). Scoped per channel /
  per recipient.
- Pure notice: explicit `"responseOptions": []` **and** `isAutoClose: true`
  closes on delivery.
- `decision` is set **only** by a `SHARED` response. A `PERSONAL` response or
  free text is never a decision.
- Polling `GET <link>/alerts/<id>` / `GET /api/v1/alerts/:id` is not
  rate-limited (sends are limited to 60/min per link/key).
- Callbacks: `callbackUrl` receives `answered` + `closed` events with an
  HMAC-SHA256 signature keyed to a per-alert secret (not used by this build;
  polling only).
- `close` (`POST <link>/close` with `{customId}` or `{alertId}`): `404` /
  `403` mean "nothing to close" and are **success**.
- Two credentials: **send link** (channel-scoped, no headers, up to 6
  response options via `respond=` parameter) and **API key** (`m91sk_…`,
  can create channels, invite recipients, alert any invited phone number).
- Send link `GET` with no `title` returns channel info (connection test,
  security control against crawlers/link previews).
- Send link `POST` accepts full payload: title, description, severity,
  responseOptions (up to 20), other, attachments, callbackUrl, isAutoClose,
  customId.
- Platform API: `POST /api/v1/recipients` invites a phone; `POST /api/v1/channels`
  creates a channel; `POST /api/v1/alerts` raises an alert to a specific phone
  or channel.
- Alert response shape: `decision` only set by `SHARED` response; `note` and
  `attachments` always present (null/[] when not given); `responses[]` includes
  name, label, effect, respondedAt, note, attachments.
- Limits: title 5–2000 chars, description up to 2000, customId up to 200,
  response options 20 by POST/6 by link, request body 1 MB, identical-payload
  window 5 seconds.
- Errors return envelope with `error.code`, `error.message`, `error.details`,
  `error.docs` (URL to troubleshooting entry).
- `delivered` counts dispatch, not a phone making a sound; the only positive
  proof of reach is a recorded response.
- `unregistered` (invited but never signed in) and `noDevice` (signed in, no
  device registered) tracked separately in send response.

## M91 CANNOT (as of this snapshot; re-verify each run)

- Alert a person who has not **accepted** their invite (`reachable: false` →
  404 `not_a_recipient`). Consent is not bypassable by any API.
- Phone people on LOW/MEDIUM. Interruption ≠ phone call.
- Send with a recipient field on the send-link form: the channel IS the
  recipient list there ("There is no recipient field at all").
- Alert a whole channel via the API key: that is the send link's job.
- Close on a `SHARED` response by default (`isAutoClose` defaults false).
- Supersede a response: one response per person, final; a reopen voids prior
  responses.
- Expire alerts server-side: **there is no `expiresIn` and no server-side
  expiry — the sender owns the deadline.**
- Distinguish a suppressed repeat from a failure purely by status code: check
  `deduplicated` before treating `delivered: 0` as a failure.
- Rule out silent drops: `delivered` counts dispatch, not a phone making a
  sound; the only positive proof is a recorded response.
- Create channels, invite members, or mint send links via API: only a person
  on a phone can do this (consent is not manufacturable).
- Rotate send links: revoking deletes the link immediately (401 on use), no
  overlap window.
- Guarantee delivery to a device with notifications denied, no network, or
  app uninstalled — such devices still count in `delivered` but make no sound.
- Make a `PERSONAL`-only alert close if a member has `noDevice` (recipient
  row stays in initial state forever).
- Carry per-alert content in the escalation phone call: the call only tells
  the person to open the app.

## Used by this build

- Review alerts: `severity: MEDIUM`, `Approve` (SHARED), `Reject` (SHARED,
  required note), `other: false`, unique `customId` per item/version/reminder
  (`blog-<date>-<slug>-v<n>` / `-r<n>`), 6-hour deadline we own.
- `notify-system`: LOW, `[]` + `isAutoClose: true`, to the primary reviewer's
  phone.
- Delivery to zero people is a failure → Writer falls back to chat approval.
- First SHARED decision wins; sibling alert closed; later/conflicting SHARED
  replies ignored and logged.