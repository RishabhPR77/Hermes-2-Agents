"""docstar_publish.py — publish an APPROVED post to Docstar via viaSocket.

Refuses to call the webhook unless the explicit approval is recorded in
data/review_queue.csv and the post is not already published. Also refuses a
slug that already exists on Docstar.

Usage:
    docstar_publish.py <post_id> <version>

Exit codes:
    0 published (or, with DOCSTAR_DRY_RUN=1, everything checked and ready)
    1 post not found in content_inventory.csv
    4 missing environment variable (webhook / shared secret)
    6 viaSocket / Docstar unreachable or returned an error envelope
    7 refused: no explicit SHARED Approve recorded for this post/version
    8 refused: slug already exists on Docstar
    9 already published (no-op)

Dry run: DOCSTAR_DRY_RUN=1 checks the refusals (7/8/9) and prints the exact
payload but does not POST to the webhook.
"""

import json
import os
import sys

import m91_common as common
import docstar_list

QUEUE_COLS = [
    "item_id", "post_id", "version", "type", "alert_id", "custom_id",
    "recipient_role", "sent_at", "deadline", "decision", "note",
    "decided_by", "decided_at", "reminders", "rollovers", "status",
    "stuck_wakes", "stuck_last_wake_at", "needs_attention",
]


def approve_label(cfg):
    return str(common.cfg_get(cfg, "review", "approve_label", default="Approve"))


def find_approval_row(rows, post_id, version):
    for r in rows:
        if r.get("post_id") == post_id and r.get("version") == str(version):
            if r.get("status") == "open" or r.get("status") == "closed":
                if r.get("decision") and r.get("decided_by") and r.get("decided_at"):
                    return r
    return None


def build_payload(cfg, post, draft_text):
    fm, body = common.split_front_matter(draft_text)
    title = (fm.get("title") or post.get("title") or "").strip()
    if not title:
        raise common.UsageError("post has no title")
    meta = (fm.get("meta_description") or fm.get("summary") or " ".join(body.split()))
    if len(meta) > 158:
        meta = meta[:155] + "..."
    tags = fm.get("tags") if isinstance(fm.get("tags"), list) else \
        common.cfg_get(cfg, "publish", "tags", default=[]) or []
    payload = {
        "action": "create",
        "mode": common.cfg_get(cfg, "publish", "mode", default="draft"),
        "title": title,
        "slug": post["slug"],
        "content_markdown": body,
        "content_html": common.markdown_to_html(body),
        "meta_description": meta,
        "tags": list(tags),
    }
    parent = common.cfg_get(cfg, "publish", "parent", default="")
    if parent:
        payload["parent"] = parent
    schema = fm.get("schema_jsonld")
    if schema:
        try:
            payload["schema_jsonld"] = json.loads(schema) if isinstance(schema, str) else schema
        except ValueError:
            payload.pop("schema_jsonld", None)
    return payload


def publish(env, cfg, payload):
    common.require_env(env, "VIASOCKET_PUBLISH_WEBHOOK", "VIASOCKET_SHARED_SECRET")
    webhook = env["VIASOCKET_PUBLISH_WEBHOOK"]
    headers = {"X-ViaSocket-Secret": env["VIASOCKET_SHARED_SECRET"]}
    if os.environ.get("DOCSTAR_DRY_RUN"):
        common.out("DRY-RUN create", webhook, common.redact(json.dumps(payload, ensure_ascii=False)))
        return {"url": "dry-run://" + payload["slug"]}
    status, envelope = common.http_request("POST", webhook, payload=payload, headers=headers)
    if status != 200:
        code, message = common.error_of(envelope)
        raise common.ApiError(status, code, "viaSocket create failed: %s" % message)
    data = common.data_of(envelope)
    if data is None:
        raise common.ApiError(status, "EMPTY", "viaSocket create returned no data")
    url = data if isinstance(data, str) else data.get("url") or data.get("live_url")
    if not url:
        raise common.ApiError(status, "NO_URL", "viaSocket create returned no url")
    return {"url": url}


def cmd_publish(env, cfg, root, args):
    if len(args) != 2:
        raise common.UsageError("usage: docstar_publish.py <post_id> <version>")
    post_id, version = args[0], str(args[1])
    inventory = common.load_inventory(root)
    post = inventory.get(post_id)
    if not post:
        common.err("post", post_id, "not found in content_inventory.csv")
        return common._EXIT_USAGE

    # refusal 9: already published
    if post.get("status") == "published" and post.get("live_url"):
        common.out(post_id, "already published at", post.get("live_url"), "— nothing to do.")
        return common._EXIT_ALREADY_PUBLISHED

    # refusal 7: explicit SHARED Approve required
    rows = common.load_queue(root)
    approval = find_approval_row(rows, post_id, version)
    if not approval or approval.get("decision") != approve_label(cfg):
        common.err(post_id, "REFUSED: no explicit SHARED",
                   approve_label(cfg),
                   "recorded for version", version, "in review_queue.csv.")
        return common._EXIT_UNAPPROVED

    # refusal 8: duplicate slug on Docstar
    existing = docstar_list.list_posts(env, cfg)
    for p in existing:
        if isinstance(p, dict) and p.get("slug") == post["slug"]:
            common.err(post_id, "REFUSED: slug", post["slug"], "already exists on Docstar.")
            return common._EXIT_DUPLICATE_SLUG

    draft_text = common.read_draft_text(root, post["draft_path"])
    payload = build_payload(cfg, post, draft_text)
    result = publish(env, cfg, payload)
    url = result["url"]
    if os.environ.get("DOCSTAR_DRY_RUN"):
        common.out(post_id, "dry run: everything checked, would publish ->", url)
        return common._EXIT_OK
    inv_rows = common.read_rows(root / "data" / "content_inventory.csv")
    fields = common.csv_fields(root / "data" / "content_inventory.csv", list(inv_rows[0].keys()) if inv_rows else [])
    for r in inv_rows:
        if r.get("id") == post_id:
            r["status"] = "published"
            r["live_url"] = url
            r["version"] = version
    common.write_rows(root / "data" / "content_inventory.csv", inv_rows, fields)

    q_rows = common.read_rows(root / "data" / "review_queue.csv")
    for r in q_rows:
        if r.get("post_id") == post_id and r.get("version") == version:
            r["status"] = "published"
    common.write_rows(root / "data" / "review_queue.csv", q_rows, QUEUE_COLS)

    package_dir = root / "ready" / ("%s-%s" % (post["date"], post["slug"]))
    package_dir.mkdir(parents=True, exist_ok=True)
    post_file = package_dir / "post.md"
    if not post_file.exists():
        post_file.write_text(draft_text, encoding="utf-8")

    common.out(post_id, "published ->", url, "(version", version + ")")
    return common._EXIT_OK


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(common.redact(__doc__))
        return common._EXIT_OK
    root = common.project_root()
    env = common.load_env()
    cfg = common.load_config()
    try:
        return cmd_publish(env, cfg, root, argv)
    except common.UsageError as e:
        common.err("docstar_publish: %s" % e)
        return common._EXIT_USAGE
    except common.EnvError as e:
        common.err("docstar_publish: %s" % e)
        return common._EXIT_ENV
    except (common.ApiError, common.NetworkError) as e:
        common.err("docstar_publish: %s" % e)
        return common._EXIT_DOCSTAR


if __name__ == "__main__":
    sys.exit(main())