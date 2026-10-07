# -*- coding: utf-8 -*-
"""Fixture helpers shared by the m91 script tests.

Tests import the scripts from scripts/ via sys.path so that the modules do
their normal `import m91_common`. Real HTTP is never touched: every entry
point is mocked in the test modules.
"""

import contextlib
import csv
import io
import pathlib
import sys
import tempfile

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

CONFIG = {
    "review": {
        "deadline_hours": 6,
        "max_rollovers": 3,
        "max_revisions": 1,
        "severity": "MEDIUM",
        "approve_label": "Approve",
        "reject_label": "Reject",
        "primary_reviewer_name": "Main reviewer",
        "backup_reviewer_name": "Backup reviewer",
    },
    "publish": {"mode": "draft", "parent": "", "tags": ["m91", "blog"]},
    "notify_system": {"severity": "LOW"},
    "topics": {"target_words": {"min": 1000, "max": 1800}},
}

DRAFT = """---
title: Human-in-the-loop approvals with M91
meta_description: How M91 keeps a human in the loop on fintech approvals.
summary: A short summary shown in the review alert.
tags: [m91, approvals]
type: article
---
# Heading

Some body text for the post.
"""

INVENTORY_CORE = dict(
    id="p1", date="2026-10-06", title="Human-in-the-loop approvals with M91",
    slug="m91-human-in-the-loop-approvals", main_keyword="m91 approvals",
    topic_group="approvals", format="article", status="draft",
    draft_path="drafts/test.md", package_path="", live_url="", version="1",
    notes="human-in-the-loop",
)


class Fixture:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "data").mkdir()
        (self.root / "drafts").mkdir()
        (self.root / "config.yaml").write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
        (self.root / "drafts" / "test.md").write_text(DRAFT, encoding="utf-8")
        (self.root / "data" / "decision_log.md").write_text("", encoding="utf-8")

    def add_inventory(self, post_id="p1", status="draft", slug=None, **overrides):
        row = dict(INVENTORY_CORE)
        row.update({"id": post_id, "status": status})
        if slug:
            row["slug"] = slug
        row.update(overrides)
        self._write_csv(self.root / "data" / "content_inventory.csv",
                        list(row.keys()), [row])
        return row

    def add_queue_row(self, **overrides):
        row = dict(
            item_id="it1", post_id="p1", version="1", type="review",
            alert_id="al1", custom_id="blog-2026-10-06-m91-human-in-the-loop-approvals-v1",
            recipient_role="main", sent_at="2026-10-06T06:00:00+00:00",
            deadline="2099-01-01T00:00:00+00:00", decision="", note="",
            decided_by="", decided_at="", reminders="0", rollovers="0", status="open",
            stuck_wakes="0", stuck_last_wake_at="", needs_attention="",
        )
        row.update(overrides)
        if row["deadline"] == "PAST":
            row["deadline"] = "2020-01-01T00:00:00+00:00"
        rows = self.queue_rows()
        rows.append(row)
        self._write_csv(self.root / "data" / "review_queue.csv",
                        list(row.keys()), rows)
        return row

    def queue_rows(self):
        path = self.root / "data" / "review_queue.csv"
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f) if r.get("item_id")]

    def _write_csv(self, path, header, rows):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(header), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    def decision_log(self):
        return (self.root / "data" / "decision_log.md").read_text(encoding="utf-8")

    def cleanup(self):
        self._tmp.cleanup()


def make_env(main="919000000001", backup="919000000002", key="sk_m91_test"):
    env = {}
    if main:
        env["M91_REVIEWER_PHONE"] = main
    if backup:
        env["M91_BACKUP_REVIEWER_PHONE"] = backup
    if key:
        env["M91_API_KEY"] = key
    return env


def run_capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = fn(*args, **kwargs)
    return code, buf.getvalue()


def decision_response(label, effect="SHARED", note=None):
    responses = [] if note is None else [{"label": label, "note": note}]
    return 200, {"success": True, "data": {
        "decision": {"label": label, "effect": effect},
        "responses": responses,
    }}


def no_decision_response():
    return 404, {"success": False, "error": {"code": "NOT_FOUND", "message": "alert not found"}}


def ok_post_response(delivered=1, deduplicated=False):
    return 200, {"success": True, "data": {
        "_id": "al_x", "delivered": delivered, "deduplicated": deduplicated,
        "customId": "blog-2026-10-06-m91-human-in-the-loop-approvals-v1",
    }}


def close_response():
    return 200, {"success": True, "data": {"closed": True}}


def reset_secrets():
    import m91_common as common
    common._SECRETS[:] = []