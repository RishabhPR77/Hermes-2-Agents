"""m91_review.py — M91 approval alerts and decision polling (Platform API).

Commands:
    raise <post_id> <version>     raise the review alert for a draft (main only)
    poll                          check open items, print the wakeAgent gate JSON
    close <post_id> <version>     close every open alert for that post/version
    notify-system <message>       LOW-severity notice (auto-close, deduped)
    wordcount <draft_path>        print the publishable-body word count + target
    invite <main|backup>          invite an M91 recipient for a reviewer role
    check                         verify the API key works

(no arguments)                  same as poll — used by the cron pre-run script (wake gate)

Exit codes:
    0 success
    1 usage / bad args / item not found in inventory or queue
    2 M91 network or API error (raise / close / notify / poll item)
    3 alert raised but delivered to zero recipients
    4 missing required environment variable or config key
    5 poll: every open item failed to be read from M91
    6 viaSocket / Docstar error (used by the docstar_* scripts)

Dry run: set M91_DRY_RUN=1 — prints the exact payloads instead of calling M91.

Secrets (API key, phones) come only from the environment. They are masked in
every message, log and write. Never printed.
"""

import datetime
import json
import os
import pathlib
import re
import sys
import uuid

import m91_common as common

QUEUE_COLS = [
    "item_id", "post_id", "version", "type", "alert_id", "custom_id",
    "recipient_role", "sent_at", "deadline", "decision", "note",
    "decided_by", "decided_at", "reminders", "rollovers", "status",
    "stuck_wakes", "stuck_last_wake_at", "needs_attention", "alert_ids",
]


def role_phone(env, role):
    key = "M91_REVIEWER_PHONE" if role == "main" else "M91_BACKUP_REVIEWER_PHONE"
    return env.get(key, "")


def other_role(role):
    return "backup" if role == "main" else "main"


def base_custom_id(post):
    return "blog-%s-%s-v%s" % (post["date"], post["slug"], post["version"])


def short_title(text, max_chars):
    """Truncate a title at a word boundary (appending …) to max_chars."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    cut = cut.rstrip()
    if not cut:
        cut = text[: max(max_chars - 1, 1)]
    return cut + "…"


def candidate_ids(base, reminders):
    ids = [base]
    for n in range(1, reminders + 1):
        ids.append("%s-r%d" % (base, n))
    return ids


def row_alert_ids(row):
    """The chain of real M91 alert _ids created for this queue row, oldest first.

    The M91 alert endpoint resolves records by the Mongo ``_id``, not by the
    human customId, so decision polling must use these. Falls back to the
    legacy ``alert_id`` column.
    """
    raw = row.get("alert_ids")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except (TypeError, ValueError):
            pass
    if row.get("alert_id"):
        return [str(row["alert_id"])]
    return []


def append_row_alert(row, alert_id):
    if not alert_id:
        return
    ids = row_alert_ids(row)
    if alert_id not in ids:
        ids.append(alert_id)
    row["alert_ids"] = json.dumps(ids)


def build_alert_payload(post, draft_text, cfg, version, deadline_hours):
    fm, body = common.split_front_matter(draft_text)
    full_title = (fm.get("title") or post.get("title") or "").strip()
    if len(full_title) < 5:
        raise common.UsageError("title must be at least 5 characters long")
    prefix = str(common.cfg_get(cfg, "review", "alert_title_prefix", default="Blog ready: "))
    max_chars = int(common.cfg_get(cfg, "review", "alert_title_max", default=48))
    title = prefix + short_title(full_title, max_chars)
    group = post.get("topic_group", "") or ""
    words = common.body_word_count(draft_text)
    summary = fm.get("summary") or fm.get("meta_description") or " ".join(body.split())[:120]
    flags = []
    notes = post.get("notes", "") or ""
    for piece in re.split(r"[;,]", notes):
        piece = piece.strip()
        if piece:
            flags.append(piece)
    ftype = str(fm.get("type") or "").strip()
    if ftype in ("update", "comparison", "rapid-response", "pinned"):
        flags.append(ftype)
    meta = []
    if group:
        meta.append("Topic group %s" % group)
    meta.extend(flags)
    meta.append("v%s" % version)
    meta.append("%d words" % words)
    lines = [" · ".join(meta)]
    warnings = []
    try:
        min_w = int(common.cfg_get(cfg, "topics", "target_words", "min"))
        max_w = int(common.cfg_get(cfg, "topics", "target_words", "max"))
    except (TypeError, ValueError):
        min_w = max_w = None
    if min_w is not None and max_w is not None and (words < min_w or words > max_w):
        warnings.append("Word count %d is outside the target of %d-%d words."
                        % (words, min_w, max_w))
    lines.append(str(summary))
    lines.append("Read it in the chat or at %s" % common.draft_rel(post.get("draft_path", "")))
    lines.extend(warnings)
    lines.append("Reminder after %s hours. Nothing is published without your approval."
                 % common.format_hours(deadline_hours))
    description = common.truncate("\n".join(lines), 2000)
    severity = str(common.cfg_get(cfg, "review", "severity", default="MEDIUM")).upper()
    if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        severity = "MEDIUM"
    approve_label = str(common.cfg_get(cfg, "review", "approve_label", default="Approve"))
    reject_label = str(common.cfg_get(cfg, "review", "reject_label", default="Reject"))
    return {
        "phone": "",  # filled by caller
        "title": title,
        "description": description,
        "severity": severity,
        "responseOptions": [
            {"label": approve_label, "effect": "SHARED"},
            {"label": reject_label, "effect": "SHARED", "required": ["note"]},
        ],
        "other": False,
    }


def send_alert(env, cfg, phone, title, description, custom_id, severity, response_options=None, is_auto_close=False):
    if phone and not re.fullmatch(r"\d{7,15}", phone):
        raise common.UsageError("phone must be a country-code number without '+' or spaces")
    payload = {
        "phone": phone,
        "title": title,
        "description": common.truncate(description or "", 2000),
        "severity": severity,
        "customId": custom_id,
        "isAutoClose": is_auto_close,
        "other": False,
    }
    if response_options is not None:
        payload["responseOptions"] = response_options
    return api_alert(env, payload)


def api_alert(env, payload):
    url = "%s/api/v1/alerts" % common.api_base(env)
    headers = {"Authorization": "Bearer %s" % env["M91_API_KEY"]}
    if os.environ.get("M91_DRY_RUN"):
        common.out("DRY-RUN POST", common.api_base(env) + "/api/v1/alerts",
                   common.redact(json.dumps(payload, ensure_ascii=False)))
        return {"_id": "dry-" + (payload.get("customId") or "alert"), "delivered": 1, "deduplicated": False}
    status, envelope = common.http_request("POST", url, payload=payload, headers=headers)
    if status in (200, 201):
        return common.data_of(envelope) or {"_id": None, "delivered": 0, "deduplicated": False}
    code, message = common.error_of(envelope)
    raise common.ApiError(status, code, message)


def read_decision(env, phone, alert_id):
    """Return (label, effect, note) or None for the alert with the given _id.

    The M91 API fetches an alert by its Mongo ``_id`` (the id returned by a
    raise/reminder POST), not by the customId. Raises ApiError on real errors.
    """
    if os.environ.get("M91_DRY_RUN"):
        return None
    url = "%s/api/v1/alerts/%s?phone=%s" % (common.api_base(env), alert_id, phone)
    headers = {"Authorization": "Bearer %s" % env["M91_API_KEY"]}
    status, envelope = common.http_request("GET", url, headers=headers)
    if status == 404:
        return None
    if status != 200:
        code, message = common.error_of(envelope)
        raise common.ApiError(status, code, message)
    data = common.data_of(envelope)
    if not isinstance(data, dict):
        return None
    decision = data.get("decision")
    if not isinstance(decision, dict) or not decision.get("label"):
        return None
    label = decision.get("label")
    effect = decision.get("effect", "SHARED")
    note = None
    for resp in data.get("responses") or []:
        if isinstance(resp, dict) and resp.get("label") == label:
            note = resp.get("note")
            break
    return label, effect, note


def close_person(env, phone, custom_id):
    """Close one person alert. 404/403 = nothing to close = success."""
    if os.environ.get("M91_DRY_RUN"):
        common.out("DRY-RUN close", custom_id)
        return True
    url = "%s/api/v1/alerts/close" % common.api_base(env)
    headers = {"Authorization": "Bearer %s" % env["M91_API_KEY"]}
    payload = {"phone": phone, "customId": custom_id}
    status, envelope = common.http_request("POST", url, payload=payload, headers=headers)
    if status in (200, 404, 403):
        return True
    code, message = common.error_of(envelope)
    raise common.ApiError(status, code, message)


def append_review_row(root, post, version, alert_id, custom_id, sent_at, deadline_iso, recipient_role):
    rows = common.read_rows(root / "data" / "review_queue.csv")
    for r in rows:
        if r.get("post_id") == post["id"] and r.get("version") == str(version) and r.get("status") == "open":
            return None, "already open: alert id %s" % r.get("alert_id")
    row = {
        "item_id": uuid.uuid4().hex[:12],
        "post_id": post["id"],
        "version": str(version),
        "type": "review",
        "alert_id": alert_id,
        "custom_id": custom_id,
        "recipient_role": recipient_role,
        "sent_at": sent_at,
        "deadline": deadline_iso,
        "decision": "",
        "note": "",
        "decided_by": "",
        "decided_at": "",
        "reminders": "0",
        "rollovers": "0",
        "status": "open",
        "stuck_wakes": "0",
        "stuck_last_wake_at": "",
        "needs_attention": "",
        "alert_ids": json.dumps([alert_id]) if alert_id else "",
    }
    rows.append(row)
    common.write_rows(root / "data" / "review_queue.csv", rows, QUEUE_COLS)
    return row, None


def set_inventory_status(root, post_id, status, **extra):
    rows = common.read_rows(root / "data" / "content_inventory.csv")
    fields = common.csv_fields(root / "data" / "content_inventory.csv", list(rows[0].keys()) if rows else [])
    changed = False
    for r in rows:
        if r.get("id") == post_id:
            r["status"] = status
            for k, v in extra.items():
                r[k] = v
            changed = True
    if changed:
        common.write_rows(root / "data" / "content_inventory.csv", rows, fields)


def append_decision_log(root, text):
    p = root / "data" / "decision_log.md"
    with p.open("a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


# --------------------------------------------------------------------------- commands
def cmd_raise(env, cfg, root, args):
    if len(args) != 2:
        raise common.UsageError("usage: m91_review.py raise <post_id> <version>")
    post_id, version = args[0], str(args[1])
    common.require_env(env, "M91_API_KEY", "M91_REVIEWER_PHONE")
    inventory = common.load_inventory(root)
    post = inventory.get(post_id)
    if not post:
        raise common.UsageError("post %s not found in content_inventory.csv" % post_id)
    deadline_hours = float(common.cfg_get(cfg, "review", "deadline_hours", default=6))
    version_label = "v%s" % version
    now = common.utc_now()
    deadline = common.deadline_from(now, deadline_hours)
    draft_text = common.read_draft_text(root, post["draft_path"])
    payload = build_alert_payload(post, draft_text, cfg, version, deadline_hours)
    payload["phone"] = role_phone(env, "main")
    custom_id = "blog-%s-%s-v%s" % (post["date"], post["slug"], version)
    payload["customId"] = custom_id
    alert_id, delivered, deduplicated = None, 0, False
    try:
        result = api_alert(env, payload)
        alert_id = result.get("_id")
        delivered = result.get("delivered", 0)
        deduplicated = bool(result.get("deduplicated"))
    except common.ApiError as e:
        # 404 = recipient never accepted an invite from this account.
        if e.status == 404:
            raise common.ApiError(404, "RECIPIENT_NOT_ACCEPTED",
                                  "reviewer has not accepted their M91 invite; run `m91_review.py invite main` first")
        raise
    if deduplicated:
        common.out("Not re-alerted: that alert is already open (customId", custom_id + ").")
    elif (delivered or 0) == 0:
        append_decision_log(root, "## %s — %s (v%s) — delivered zero\n\n- **Type:** not-approval\n- **What happened:** alert raised but M91 delivered it to zero people (id %s)\n- **Action taken:** Writer falls back to chat approval\n" % (common.utc_now().date(), post_id, version, alert_id))
        raise ZeroDeliveredError("alert raised but delivered to 0 people (id %s)" % alert_id)
    row, warn = append_review_row(root, post, version, alert_id or "", custom_id,
                                  now.isoformat(timespec="seconds"), deadline, "main")
    if warn:
        common.out(warn)
    else:
        common.out("Alert raised (customId %s, id %s), delivered to %s." % (custom_id, alert_id, delivered))
    set_inventory_status(root, post_id, "awaiting_review")
    return common._EXIT_OK


class ZeroDeliveredError(Exception):
    pass


def cmd_close(env, cfg, root, args):
    if len(args) != 2:
        raise common.UsageError("usage: m91_review.py close <post_id> <version>")
    post_id, version = args[0], str(args[1])
    common.require_env(env, "M91_API_KEY")
    rows = common.load_queue(root)
    matches = [r for r in rows if r.get("post_id") == post_id and r.get("version") == version]
    if not matches:
        common.err("no queue row for post %s version %s" % (post_id, version))
        return common._EXIT_USAGE
    failures = 0
    for row in matches:
        base = row.get("custom_id")
        reminders = int(row.get("reminders", "0") or "0")
        ids = candidate_ids(base, reminders)
        role = row.get("recipient_role") or "main"
        roles = {role, other_role(role)}
        for rl in sorted(roles):
            phone = role_phone(env, rl)
            if not phone:
                continue
            for cid in ids:
                try:
                    close_person(env, phone, cid)
                except common.ApiError as e:
                    common.err("close failed for", cid, ":", str(e))
                    failures += 1
        if row.get("status") == "open":
            row["status"] = "closed"
    common.write_rows(root / "data" / "review_queue.csv", rows, QUEUE_COLS)
    if failures:
        return common._EXIT_API
    common.out("Closed alerts for %s v%s." % (post_id, version))
    return common._EXIT_OK


def cmd_notify(env, cfg, root, args):
    if not args:
        raise common.UsageError("usage: m91_review.py notify-system <message>")
    message = " ".join(args)
    common.require_env(env, "M91_API_KEY", "M91_REVIEWER_PHONE")
    severity = str(common.cfg_get(cfg, "notify_system", "severity", default="LOW")).upper()
    import hashlib
    custom_id = "blog-sys-" + hashlib.sha1(message.encode("utf-8")).hexdigest()[:12]
    try:
        result = send_alert(
            env, cfg, role_phone(env, "main"),
            title="M91 blog system notice",
            description=message,
            custom_id=custom_id,
            severity=severity,
            response_options=[],
            is_auto_close=True,
        )
    except common.ApiError as e:
        raise e
    if bool(result.get("deduplicated")):
        common.out("System notice not re-sent: already open (customId", custom_id + ").")
    elif (result.get("delivered", 0) or 0) == 0:
        raise ZeroDeliveredError("system notice delivered to 0 people")
    common.out("System notice sent (customId", custom_id + ").")
    return common._EXIT_OK


def cmd_invite(env, cfg, root, args):
    if len(args) != 1 or args[0] not in ("main", "backup"):
        raise common.UsageError("usage: m91_review.py invite <main|backup>")
    role = args[0]
    common.require_env(env, "M91_API_KEY")
    phone = role_phone(env, role)
    if not phone:
        raise common.EnvError("missing environment variable %s" % ("M91_REVIEWER_PHONE" if role == "main" else "M91_BACKUP_REVIEWER_PHONE"))
    label = common.cfg_get(cfg, "review", "primary_reviewer_name" if role == "main" else "backup_reviewer_name", default=role)
    url = "%s/api/v1/recipients" % common.api_base(env)
    payload = {"phone": phone, "label": label}
    headers = {"Authorization": "Bearer %s" % env["M91_API_KEY"]}
    if os.environ.get("M91_DRY_RUN"):
        common.out("DRY-RUN invite", role, "->", common.redact(json.dumps(payload)))
        return common._EXIT_OK
    status, envelope = common.http_request("POST", url, payload=payload, headers=headers)
    if status not in (200, 201):
        code, message = common.error_of(envelope)
        raise common.ApiError(status, code, message)
    data = common.data_of(envelope) or {}
    state = data.get("state")
    reachable = data.get("reachable")
    if state == "accepted":
        common.out("%s invited and accepted, reachable=%s." % (role, reachable))
    elif state == "pending":
        common.out("%s invited — must install M91, sign in with this number and accept before alerts reach them." % role)
    elif state == "declined":
        common.out("%s has declined previously." % role)
    else:
        common.out("%s invite state=%s reachable=%s." % (role, state, reachable))
    return common._EXIT_OK


def cmd_check(env, cfg, root, args):
    common.require_env(env, "M91_API_KEY")
    url = "%s/api/v1/me" % common.api_base(env)
    headers = {"Authorization": "Bearer %s" % env["M91_API_KEY"]}
    status, envelope = common.http_request("GET", url, headers=headers)
    if status != 200:
        code, message = common.error_of(envelope)
        raise common.ApiError(status, code, message)
    data = common.data_of(envelope) or {}
    common.out("M91 API key is live. Label:", data.get("label"), "| Owner:", data.get("owner"))
    return common._EXIT_OK


# --------------------------------------------------------------------------- wordcount
def cmd_wordcount(env, cfg, root, args):
    if len(args) != 1:
        raise common.UsageError("usage: m91_review.py wordcount <draft_path>")
    words = common.body_word_count(common.read_draft_text(root, args[0]))
    min_w = common.cfg_get(cfg, "topics", "target_words", "min")
    max_w = common.cfg_get(cfg, "topics", "target_words", "max")
    try:
        tmin, tmax = int(min_w), int(max_w)
    except (TypeError, ValueError):
        tmin = tmax = None
    common.out("wordcount:", words)
    if tmin is not None and tmax is not None:
        common.out("target:", "%d-%d" % (tmin, tmax))
        status = "OK" if tmin <= words <= tmax else ("OVER" if words > tmax else "UNDER")
        common.out("status:", status)
    else:
        common.out("target: unset")
        common.out("status: OK")
    return common._EXIT_OK


# --------------------------------------------------------------------------- rate-limit watchdog
_RATE_LIMIT_RE = re.compile(r"(?i)(429|rate\s*limit|quota|free-models-per-day|too\s+many\s+requests)")


def audit_path():
    """Path to the Hermes cron usage-audit ledger, if it exists.

    Override with M91_AUDIT_PATH (used by tests); otherwise derived from
    HERMES_HOME. Returns None when there is no ledger to watch.
    """
    override = os.environ.get("M91_AUDIT_PATH")
    if override:
        return pathlib.Path(override)
    home = os.environ.get("HERMES_HOME")
    if not home:
        return None
    p = pathlib.Path(home) / "cron" / "usage_audit.jsonl"
    return p if p.is_file() else None


def scan_audit_429s(root, now, window_minutes=20):
    """Return rate-limited cron attempts from the usage-audit ledger.

    Only attempts whose error mentions a rate limit and whose timestamp is
    within ``window_minutes`` of ``now`` are returned, newest first. The
    project root is unused but kept so tests can seed a ledger next to it.
    """
    path = audit_path()
    if path is None or not path.is_file():
        return []
    threshold = now - datetime.timedelta(minutes=window_minutes)
    hits = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            error = str(rec.get("error") or "")
            ts = rec.get("ts") or ""
            if not error or not ts or not _RATE_LIMIT_RE.search(error):
                continue
            try:
                t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if t < threshold or t > now + datetime.timedelta(minutes=2):
                continue
            hits.append({
                "fire_id": str(rec.get("fire_id") or ""),
                "job_id": str(rec.get("job_id") or ""),
                "ts": ts,
                "error": error,
            })
    hits.sort(key=lambda r: r["ts"], reverse=True)
    return hits


def _write_json(path, data):
    tmp = "%s.tmp" % path
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _notify_cron_429s(env, cfg, root, now):
    """Watchdog: a rate-limited cron run is never silent.

    Runs inside every poll (no model call). Sends one LOW notify-system per
    failed attempt (deduplicated via data/cron_429_sent.json). When M91
    delivery is not configured yet it records the gap instead of crashing,
    so the miss stays visible in the script output.
    """
    window = int(common.cfg_get(cfg, "review", "cron_429_window_minutes", default=20))
    entries = scan_audit_429s(root, now, window)
    if not entries:
        return
    sent_path = root / "data" / "cron_429_sent.json"
    sent = {}
    if sent_path.is_file():
        try:
            sent = json.loads(sent_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            sent = {}
    main_phone = role_phone(env, "main")
    if not env.get("M91_API_KEY") or not main_phone:
        for e in entries:
            if e["fire_id"] and e["fire_id"] not in sent:
                common.err("rate-limited cron run not notified: M91_API_KEY or reviewer"
                           " phone not set (fire", e["fire_id"] + ")")
                sent[e["fire_id"]] = "unnotified-missing-env"
        _write_json(sent_path, sent)
        return
    severity = str(common.cfg_get(cfg, "notify_system", "severity", default="LOW")).upper()
    if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        severity = "LOW"
    for e in entries:
        fid = e["fire_id"]
        if not fid or fid in sent:
            continue
        description = common.truncate(
            "M91 blog cron run ended with a provider rate limit.\n"
            "Job: %s | attempt: %s | at: %s UTC\n"
            "Error: %s" % (e["job_id"], fid, e["ts"], common.redact(e["error"])), 2000)
        try:
            result = send_alert(env, cfg, main_phone,
                                title="M91 blog rate-limited cron run",
                                description=description,
                                custom_id="blog-sys-cron429-%s" % fid[:12],
                                severity=severity,
                                response_options=[],
                                is_auto_close=True)
            sent[fid] = "sent"
            if (result.get("delivered", 0) or 0) == 0 and not result.get("deduplicated"):
                common.err("rate-limit notice for", fid, "delivered to 0 people")
            common.out("rate-limited cron run", fid, "notified.")
        except (common.ApiError, common.NetworkError) as exc:
            common.err("rate-limit notice failed for", fid, ":", str(exc))
            sent[fid] = "failed"
    _write_json(sent_path, sent)


# --------------------------------------------------------------------------- poll
def _handle_stuck(env, cfg, root, open_rows, inventory, now, approve_label, reject_label,
                  changes, failures):
    """Detect decided-but-unactioned rows and re-wake the agent (or escalate).

    A row with a reviewer decision (approve/reject) normally stays open only while
    the agent is acting on it (publish + close, or revise + raise). If it is still
    open after ``review.stuck_after_minutes`` (default 30) since the decision (or
    since the last stuck re-wake), the agent apparently failed to finish. We
    re-wake it up to ``review.max_stuck_wakes`` (default 3) times; after that we
    send a LOW ``notify-system`` notice to the primary reviewer and flag the row
    ``needs_attention``. Grace is measured from the last wake, so attempts are
    spaced ≥ ``stuck_after_minutes`` apart. Returns the updated failure count.
    """
    stuck_after_minutes = float(common.cfg_get(cfg, "review", "stuck_after_minutes", default=30))
    max_stuck_wakes = int(common.cfg_get(cfg, "review", "max_stuck_wakes", default=3))
    severity = str(common.cfg_get(cfg, "notify_system", "severity", default="LOW")).upper()
    if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        severity = "LOW"
    grace = datetime.timedelta(minutes=stuck_after_minutes)
    main_phone = role_phone(env, "main")
    for row in open_rows:
        decision = row.get("decision") or ""
        if decision not in (approve_label, reject_label):
            continue  # only reviewer decisions require the agent to finish a job
        if row.get("status") != "open" or row.get("needs_attention"):
            continue
        post_id = row.get("post_id")
        version = row.get("version")
        decided_at = common.parse_ts(row.get("decided_at"))
        if not decided_at:
            continue
        last_wake_at = common.parse_ts(row.get("stuck_last_wake_at"))
        if (now - (last_wake_at or decided_at)) < grace:
            continue  # still inside grace: the agent may still be working
        wake_count = int(row.get("stuck_wakes") or "0")
        item = {"item_id": row.get("item_id"), "post_id": post_id, "version": version,
                "custom_id": row.get("custom_id", ""), "recipient_role": row.get("recipient_role", ""),
                "draft_path": (inventory.get(post_id) or {}).get("draft_path", "")}
        if wake_count >= max_stuck_wakes:
            # Re-wakes exhausted: LOW notice to the primary reviewer, flag, stop waking.
            if not main_phone:
                common.err("no primary reviewer phone; cannot report stuck item", row.get("item_id"))
                failures += 1
                continue
            custom_id = "blog-sys-stuck-%s-v%s" % (post_id, version)
            description = common.truncate(
                "M91 blog: %s v%s is stuck. The %s decision recorded at %s UTC was not "
                "actioned after %s re-wakes. Draft: %s. Check the review queue "
                "and Docstar." % (post_id, version, decision, row.get("decided_at"),
                                  max_stuck_wakes, common.draft_rel(item["draft_path"])), 2000)
            try:
                result = send_alert(env, cfg, main_phone,
                                    title="M91 blog stuck item %s v%s" % (post_id, version),
                                    description=description,
                                    custom_id=custom_id,
                                    severity=severity,
                                    response_options=[],
                                    is_auto_close=True)
            except (common.ApiError, common.NetworkError) as exc:
                common.err("stuck notice failed for", post_id, ":", str(exc))
                failures += 1
                continue
            if (result.get("delivered", 0) or 0) == 0 and not result.get("deduplicated"):
                common.err("stuck notice for", post_id, "delivered to 0 people")
                failures += 1
                continue
            row["needs_attention"] = "yes"
            common.out(post_id, "v" + str(version), "stuck: notice sent, flagged needs_attention.")
            continue  # no agent wake for an exhausted item
        wake_count += 1
        row["stuck_wakes"] = str(wake_count)
        row["stuck_last_wake_at"] = now.isoformat(timespec="seconds")
        changes.append(dict(item, decision="stuck", stuck_wake=str(wake_count),
                            of=str(max_stuck_wakes), original_decision=decision))
        common.out(post_id, "v" + str(version), "stuck: decision un-actioned; wake %s of %s"
                    % (wake_count, max_stuck_wakes))
    return failures


def cmd_poll(env, cfg, root, args):
    approve_label = str(common.cfg_get(cfg, "review", "approve_label", default="Approve"))
    reject_label = str(common.cfg_get(cfg, "review", "reject_label", default="Reject"))
    max_rollovers = int(common.cfg_get(cfg, "review", "max_rollovers", default=3))
    max_revisions = int(common.cfg_get(cfg, "review", "max_revisions", default=1))
    deadline_hours = float(common.cfg_get(cfg, "review", "deadline_hours", default=6))
    now = common.utc_now()

    # Rule 5: a rate-limited cron run is never silent — notify before anything
    # else, whether or not there are open review items.
    _notify_cron_429s(env, cfg, root, now)

    rows = common.load_queue(root)
    inventory = common.load_inventory(root)
    open_rows = [r for r in rows if r.get("status") == "open"]
    if not open_rows:
        common.out(json.dumps({"wakeAgent": False}))
        return common._EXIT_OK

    had_decision = {r.get("item_id"): r.get("decision") for r in open_rows if r.get("decision")}
    changes = []
    failures = 0

    for row in open_rows:
        post = inventory.get(row.get("post_id"))
        post_id = row.get("post_id")
        version = row.get("version")
        base = row.get("custom_id") or ""
        role = row.get("recipient_role") or "main"
        phone = role_phone(env, role)
        reminders = int(row.get("reminders", "0") or "0")
        cids = candidate_ids(base, reminders)
        aids = row_alert_ids(row)
        item = {"item_id": row.get("item_id"), "post_id": post_id, "version": version,
                "custom_id": base, "recipient_role": role, "draft_path": (post or {}).get("draft_path", "")}
        # -- already decided: only detect later/conflicting decisions -----------
        if not phone:
            err_line = "missing phone env for role %s (item %s)" % (role, row.get("item_id"))
            common.err(err_line)
            failures += 1
            continue
        found = None
        try:
            for aid in aids or [row.get("custom_id", "")]:
                if not aid:
                    continue
                found = read_decision(env, phone, aid)
                if found:
                    break
        except common.ApiError as e:
            common.err("could not read decision for", cid, ":", str(e))
            failures += 1
            continue
        except common.NetworkError as e:
            common.err("could not reach M91 for", post_id, ":", str(e))
            failures += 1
            continue

        if row.get("decision"):
            if found:
                label, effect, note = found
                if effect != "SHARED" or (label != approve_label and label != reject_label):
                    continue
                if label != row.get("decision"):
                    entry = ("## %s — %s (v%s) — conflicting late decision\n\n"
                             "- **Type:** conflicting-reply\n"
                             "- **What happened:** %s replied '%s' after %s decided '%s' (item %s)\n"
                             "- **Action taken:** ignored; first SHARED decision (%s) already recorded\n"
                             % (now.date(), post_id, version, role, common.redact(str(label)),
                                row.get("decided_by"), row.get("decision"), row.get("item_id"), row.get("decision")))
                    append_decision_log(root, entry)
                    common.err("conflicting decision for", post_id, "ignored and logged")
            continue  # never re-wake for a decided item

        if found and found[1] == "SHARED":
            label, effect, note = found
            if label not in (approve_label, reject_label):
                continue
            row["decision"] = label
            row["decided_by"] = role
            row["decided_at"] = now.isoformat(timespec="seconds")
            if note:
                row["note"] = common.truncate(str(note), 2000)
            decision_kind = "approve" if label == approve_label else "reject"
            skipped = False
            if decision_kind == "reject":
                rejections = sum(1 for r in rows if r.get("post_id") == post_id and r.get("decision") == reject_label)
                if rejections > max_revisions:
                    row["status"] = "skipped"
                    skipped = True
                    row["note"] = ((row.get("note") or "") + " | skipped: max_revisions reached").strip(" |")
                    common.out(post_id, "rejected past max_revisions; skipped.")
            common.out(post_id, "v" + str(version), "->", decision_kind, "by", role)
            # close sibling + our own reminder alerts (first SHARED decision wins)
            for rl in (role, other_role(role)):
                p = role_phone(env, rl)
                if not p:
                    continue
                for cid in cids:
                    try:
                        close_person(env, p, cid)
                    except (common.ApiError, common.NetworkError):
                        pass
            changes.append(dict(item, decision=decision_kind, note=row.get("note"),
                                decider=role, skipped=skipped))
            continue

        # -- no decision yet: deadline handling --------------------------------
        deadline = common.parse_ts(row.get("deadline"))
        if deadline and now >= deadline:
            if (int(row.get("rollovers", "0") or "0") + 1) > max_rollovers:
                row["status"] = "skipped"
                row["note"] = (row.get("note") or "") + " | skipped: max rollovers reached"
                common.out(post_id, "skipped: max rollovers reached (no decision).")
                changes.append(dict(item, decision="deadline_passed", skipped=True, note=row.get("note"), decider=""))
                continue
            rollovers = int(row.get("rollovers", "0") or "0") + 1
            reminders_new = reminders + 1
            row["rollovers"] = str(rollovers)
            row["reminders"] = str(reminders_new)
            row["deadline"] = common.deadline_from(now, deadline_hours)
            row["sent_at"] = now.isoformat(timespec="seconds")
            if role == "main":
                # close main, raise to backup reviewer with the same custom id
                for cid in cids:
                    try:
                        close_person(env, phone, cid)
                    except (common.ApiError, common.NetworkError):
                        pass
                backup_phone = role_phone(env, "backup")
                if not backup_phone:
                    common.err("no backup phone configured; cannot escalate item", row.get("item_id"))
                    failures += 1
                    continue
                post2 = inventory.get(post_id)
                payload = build_alert_payload(post2, common.read_draft_text(root, (post2 or {}).get("draft_path", "")), cfg,
                                              str(version), deadline_hours)
                payload["phone"] = backup_phone
                payload["customId"] = base
                result = api_alert(env, payload)
                row["recipient_role"] = "backup"
                row["alert_id"] = result.get("_id", "")
                append_row_alert(row, result.get("_id", ""))
                if (result.get("delivered", 0) or 0) == 0 and not result.get("deduplicated"):
                    failures += 1
                common.out(post_id, "deadline: main closed, backup reviewer alerted (rollover", str(rollovers) + ").")
                changes.append(dict(item, decision="deadline_passed", skipped=False, note="", decider="backup"))
            else:
                reminder_id = "%s-r%s" % (base, reminders_new)
                payload = build_alert_payload(post, common.read_draft_text(
                    root, (inventory.get(post_id) or {}).get("draft_path", "")), cfg, str(version), deadline_hours)
                payload["phone"] = phone
                payload["customId"] = reminder_id
                result = api_alert(env, payload)
                append_row_alert(row, result.get("_id", ""))
                if (result.get("delivered", 0) or 0) == 0 and not result.get("deduplicated"):
                    failures += 1
                common.out(post_id, "deadline: reminder", reminder_id, "sent (rollover", str(rollovers) + ").")
                changes.append(dict(item, decision="deadline_passed", skipped=False, note="", decider=""))
            row.pop("custom_marker", None)
            continue
        # nothing changed for this item

    failures = _handle_stuck(env, cfg, root, open_rows, inventory, now,
                             approve_label, reject_label, changes, failures)

    common.write_rows(root / "data" / "review_queue.csv", rows, QUEUE_COLS)

    if changes:
        gate = {"wakeAgent": True, "context": {
            "items": changes,
            "config": {"max_revisions": max_revisions, "max_rollovers": max_rollovers,
                       "approve_label": approve_label, "reject_label": reject_label},
        }}
    else:
        gate = {"wakeAgent": False}
    common.out(json.dumps(gate))
    if failures and failures == len(open_rows):
        return common._EXIT_POLL_ALL_FAILED
    return common._EXIT_OK


# --------------------------------------------------------------------------- main
COMMANDS = {
    "raise": cmd_raise,
    "poll": cmd_poll,
    "close": cmd_close,
    "notify-system": cmd_notify,
    "wordcount": cmd_wordcount,
    "invite": cmd_invite,
    "check": cmd_check,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(common.redact(__doc__))
        return common._EXIT_OK
    if not argv:
        # No arguments = run poll (used by the cron pre-run script / wake gate,
        # which cannot pass argv). Poll prints the wakeAgent gate JSON last.
        cmd, args = "poll", []
    else:
        cmd, args = argv[0], argv[1:]
    if cmd not in COMMANDS:
        common.err("unknown command:", cmd)
        return common._EXIT_USAGE
    root = common.project_root()
    env = common.load_env()
    cfg = common.load_config()
    try:
        return COMMANDS[cmd](env, cfg, root, args)
    except common.UsageError as e:
        common.err("m91_review: %s" % e)
        return common._EXIT_USAGE
    except common.EnvError as e:
        common.err("m91_review: %s" % e)
        return common._EXIT_ENV
    except ZeroDeliveredError as e:
        common.err("m91_review: %s" % e)
        return common._EXIT_ZERO_DELIVERED
    except common.ApiError as e:
        common.err("m91_review: %s" % e)
        return common._EXIT_API
    except common.NetworkError as e:
        common.err("m91_review: could not reach M91 (%s)" % e)
        return common._EXIT_API


if __name__ == "__main__":
    sys.exit(main())