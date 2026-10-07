# -*- coding: utf-8 -*-
"""Unit tests for m91_review.py (raise / poll / close / notify) with mocks.

Covers the agreed cases:
  - approve (SHARED) recorded, wakes agent
  - reject with note recorded
  - second rejection -> skipped (max_revisions)
  - deadline -> backup reviewer + reminder, rollover increments
  - deadline rollover limit -> skipped
  - free-text / PERSONAL reply is not a decision
  - alert delivered to zero recipients -> exit 3
  - duplicate decision event is idempotent (no repeat wake)
  - conflicting late decision is ignored and logged
  - M91 unreachable -> poll exit 5 when every item fails
  - secrets are never printed (redaction)
"""

import datetime
import json
import os
import unittest
from unittest import mock

import fixtures as fx
import m91_common as common
import m91_review


def json_wake(out):
    """Return True if the poll printed a gate JSON with wakeAgent: true."""
    gate = last_gate(out)
    return bool(gate) and bool(gate.get("wakeAgent"))


def last_gate(out):
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if "wakeAgent" in parsed:
                return parsed
    return None


class ReviewTestBase(unittest.TestCase):
    def setUp(self):
        fx.reset_secrets()
        self.fx = fx.Fixture()
        self.addCleanup(self.fx.cleanup)
        self.env = fx.make_env()
        self.cfg = common.load_config(self.fx.root / "config.yaml")
        os.environ["M91_BLOG_ROOT"] = str(self.fx.root)
        os.environ["M91_API_KEY"] = self.env["M91_API_KEY"]
        os.environ["M91_REVIEWER_PHONE"] = self.env["M91_REVIEWER_PHONE"]
        os.environ["M91_BACKUP_REVIEWER_PHONE"] = self.env["M91_BACKUP_REVIEWER_PHONE"]
        self.fx.add_inventory()

    def tearDown(self):
        for k in ("M91_BLOG_ROOT", "M91_API_KEY", "M91_REVIEWER_PHONE",
                  "M91_BACKUP_REVIEWER_PHONE"):
            os.environ.pop(k, None)

    def run_poll(self):
        return fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])


FAKE_NOW = datetime.datetime(2026, 10, 7, 12, 0, tzinfo=datetime.timezone.utc)


class TestRaise(ReviewTestBase):
    def test_raise_records_queue_and_inventory(self):
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response()) as req:
            code = m91_review.main(["raise", "p1", "1"])
        self.assertEqual(code, common._EXIT_OK)
        rows = self.fx.queue_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recipient_role"], "main")
        self.assertEqual(rows[0]["decision"], "")
        self.assertTrue(rows[0]["alert_id"])
        self.assertEqual(rows[0]["custom_id"],
                         "blog-2026-10-06-m91-human-in-the-loop-approvals-v1")
        deadline = common.parse_ts(rows[0]["deadline"])
        self.assertIsNotNone(deadline)
        self.assertTrue(deadline > common.utc_now())
        posts = common.load_inventory(self.fx.root)
        self.assertEqual(posts["p1"]["status"], "awaiting_review")
        url = req.call_args[0][1]
        payload = req.call_args[1]["payload"]
        self.assertTrue(url.endswith("/api/v1/alerts"))
        self.assertEqual(payload["customId"],
                         "blog-2026-10-06-m91-human-in-the-loop-approvals-v1")
        self.assertTrue(payload["title"].startswith("Blog ready: "))
        self.assertTrue(payload["description"].startswith("Topic group approvals ·"))
        self.assertIn("Nothing is published without your approval.", payload["description"])
        self.assertNotIn("drafts/drafts", payload["description"])
        opt_labels = [r["label"] for r in payload["responseOptions"]]
        self.assertIn("Approve", opt_labels)
        self.assertIn("Reject", opt_labels)

    def test_raise_duplicate_alert_is_single_row(self):
        self.fx.add_queue_row()
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response()):
            code = m91_review.main(["raise", "p1", "1"])
        self.assertEqual(code, common._EXIT_OK)
        self.assertEqual(len(self.fx.queue_rows()), 1)

    def test_raise_zero_delivered_exits_3(self):
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response(delivered=0)):
            code = m91_review.main(["raise", "p1", "1"])
        self.assertEqual(code, common._EXIT_ZERO_DELIVERED)

    def test_raise_unknown_post_exits_1(self):
        code = m91_review.main(["raise", "ghost", "1"])
        self.assertEqual(code, common._EXIT_USAGE)

    def test_raise_missing_env_exits_4(self):
        with mock.patch("m91_review.common.load_env", return_value={}):
            code = m91_review.main(["raise", "p1", "1"])
        self.assertEqual(code, common._EXIT_ENV)


class PollMockSideEffect:
    """Scripted responses consumed in call order, ignoring method/url."""

    def __init__(self, responses):
        self.q = list(responses)

    def __call__(self, method, url, payload=None, headers=None, timeout=30):
        return self.q.pop(0)


class TestPollDecisions(ReviewTestBase):
    def test_decision_read_uses_alert_id_not_custom_id(self):
        # Live regression: the M91 alert endpoint resolves by Mongo _id, and
        # polling by customId returned 404 (no decision ever seen).
        self.fx.add_queue_row(alert_id="al1")
        calls = []

        def fake(method, url, payload=None, headers=None, timeout=30):
            calls.append((method, url))
            if method == "GET":
                return fx.decision_response("Approve")
            return fx.close_response()

        with mock.patch("m91_review.common.http_request", side_effect=fake):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        get_urls = [u for m, u in calls if m == "GET"]
        self.assertTrue(any("/api/v1/alerts/al1?" in u for u in get_urls))
        self.assertFalse(any("blog-2026-10-06" in u for u in get_urls))
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["decision"], "Approve")

    def test_approve_recorded_and_wakes(self):
        self.fx.add_queue_row()
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Approve", note="looks good"),
                            fx.close_response(),   # close main
                            fx.close_response(),   # close backup
                        ])):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["decision"], "Approve")
        self.assertEqual(row["decided_by"], "main")
        self.assertEqual(row["note"], "looks good")
        gate = last_gate(out)
        self.assertTrue(gate["wakeAgent"])
        self.assertEqual(gate["context"]["items"][0]["decision"], "approve")

    def test_reject_with_note(self):
        self.fx.add_queue_row()
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Reject", note="reword the intro"),
                            fx.close_response(),
                            fx.close_response(),
                        ])):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["decision"], "Reject")
        self.assertEqual(row["note"], "reword the intro")
        self.assertTrue(json_wake(out))

    def test_second_rejection_skips(self):
        self.fx.add_queue_row(item_id="it1")
        self.fx.add_queue_row(item_id="it2", version="2")
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Reject", note="again"),
                            fx.close_response(), fx.close_response(),
                            fx.decision_response("Reject", note="still no"),
                            fx.close_response(), fx.close_response(),
                        ])):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        rows = {r["item_id"]: r for r in self.fx.queue_rows()}
        self.assertEqual(rows["it1"]["status"], "open")
        self.assertEqual(rows["it2"]["status"], "skipped")
        self.assertIn("skipped", out)

    def test_free_text_reply_is_not_a_decision(self):
        # A PERSONAL reply leaves data.decision null; M91 reports no decision.
        self.fx.add_queue_row()
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([fx.no_decision_response()])):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))
        self.assertEqual(self.fx.queue_rows()[0]["decision"], "")

    def test_conflicting_late_decision_logged_ignored(self):
        decided_at = (FAKE_NOW - datetime.timedelta(minutes=5)).isoformat(timespec="seconds")
        self.fx.add_queue_row(decision="Approve", decided_by="main", decided_at=decided_at)
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Reject", note="late"),
                        ])), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))
        self.assertEqual(self.fx.queue_rows()[0]["decision"], "Approve")
        self.assertIn("conflicting", self.fx.decision_log().lower())

    def test_duplicate_decision_event_is_idempotent(self):
        self.fx.add_queue_row()
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Approve"),
                            fx.close_response(), fx.close_response(),
                        ])):
            code1, _ = self.run_poll()
        self.assertEqual(code1, common._EXIT_OK)
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.decision_response("Approve"),
                            fx.close_response(), fx.close_response(),
                        ])):
            code2, out2 = self.run_poll()
        self.assertEqual(code2, common._EXIT_OK)
        self.assertFalse(json_wake(out2))


class TestPollDeadline(ReviewTestBase):
    def run_poll(self):
        return fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])

    def test_deadline_escalates_to_backup(self):
        self.fx.add_queue_row(deadline="PAST")
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.no_decision_response(),   # GET base (main, none)
                            fx.close_response(),         # close main base
                            fx.ok_post_response(),       # alert backup
                        ])), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["recipient_role"], "backup")
        self.assertEqual(row["rollovers"], "1")
        self.assertEqual(row["reminders"], "1")
        gate = last_gate(out)
        self.assertEqual(gate["context"]["items"][0]["decision"], "deadline_passed")

    def test_deadline_backup_reminder_chain(self):
        self.fx.add_queue_row(recipient_role="backup", rollovers="2", reminders="2",
                              deadline="PAST")
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.no_decision_response(),   # GET alert al1 (none)
                            fx.ok_post_response(),       # POST reminder base-r3
                        ])), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW):
            code, _ = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["rollovers"], "3")
        self.assertEqual(row["reminders"], "3")
        self.assertEqual(row["recipient_role"], "backup")

    def test_deadline_rollover_limit_skips(self):
        self.fx.add_queue_row(deadline="PAST", rollovers="3", reminders="3")
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.no_decision_response(),   # base
                            fx.no_decision_response(),   # r1
                            fx.no_decision_response(),   # r2
                            fx.no_decision_response(),   # r3
                        ])), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW):
            code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["status"], "skipped")
        self.assertIn("skipped", out)


class TestPollFailures(ReviewTestBase):
    def test_missing_backup_phone_counts_as_failure(self):
        self.fx.add_queue_row(deadline="PAST")
        env = fx.make_env()
        env.pop("M91_BACKUP_REVIEWER_PHONE")
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect([
                            fx.no_decision_response(),   # GET base (main, none)
                            fx.close_response(),         # close main base
                        ])), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW):
            code, _ = fx.run_capture(m91_review.cmd_poll, env, self.cfg, self.fx.root, [])
        self.assertEqual(code, common._EXIT_POLL_ALL_FAILED)

    def test_network_error_all_failed_exits_5(self):
        self.fx.add_queue_row()

        def boom(method, url, payload=None, headers=None, timeout=30):
            raise common.NetworkError("unreachable")

        with mock.patch("m91_review.common.http_request", side_effect=boom):
            code, _ = self.run_poll()
        self.assertEqual(code, common._EXIT_POLL_ALL_FAILED)

    def test_no_open_items_quiet(self):
        code, out = self.run_poll()
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))


class TestPollStuck(ReviewTestBase):
    """Stuck rows: decided but un-actioned after the grace period are re-woken at
    most review.max_stuck_wakes times; then a LOW notice is sent and the row is
    flagged needs_attention (no further wakes)."""

    STUCK = dict(decision="Approve", decided_by="main",
                 decided_at="2026-10-07T11:20:00+00:00")  # 40 min before FAKE_NOW

    def run_poll(self, now=FAKE_NOW, responses=()):
        with mock.patch("m91_review.common.http_request",
                        side_effect=PollMockSideEffect(list(responses))), \
             mock.patch("m91_review.common.utc_now", return_value=now):
            return fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])

    def test_stuck_row_within_grace_does_not_wake(self):
        decided_at = (FAKE_NOW - datetime.timedelta(minutes=5)).isoformat(timespec="seconds")
        self.fx.add_queue_row(**dict(self.STUCK, decided_at=decided_at))
        code, out = self.run_poll(responses=[fx.decision_response("Approve")])
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["stuck_wakes"], "0")
        self.assertEqual(row["needs_attention"], "")

    def test_stuck_row_after_grace_wakes_and_counts(self):
        self.fx.add_queue_row(**self.STUCK)
        code, out = self.run_poll(now=FAKE_NOW, responses=[fx.decision_response("Approve")])
        self.assertEqual(code, common._EXIT_OK)
        gate = last_gate(out)
        self.assertTrue(gate["wakeAgent"])
        item = gate["context"]["items"][0]
        self.assertEqual(item["decision"], "stuck")
        self.assertEqual(item["stuck_wake"], "1")
        self.assertEqual(item["original_decision"], "Approve")
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["stuck_wakes"], "1")
        self.assertEqual(row["stuck_last_wake_at"], FAKE_NOW.isoformat(timespec="seconds"))

    def test_stuck_wake_increments_each_grace_period(self):
        # 1st wake already emitted; 40 more minutes pass -> 2nd, then 3rd.
        self.fx.add_queue_row(**self.STUCK)
        self.fx.queue_rows()
        rows = self.fx.queue_rows()
        rows[0]["stuck_wakes"] = "1"
        rows[0]["stuck_last_wake_at"] = "2026-10-07T12:00:00+00:00"  # FAKE_NOW
        fx.Fixture._write_csv(self.fx, self.fx.root / "data" / "review_queue.csv",
                              list(rows[0].keys()), rows)
        t2 = FAKE_NOW + datetime.timedelta(minutes=40)
        code, out = self.run_poll(now=t2, responses=[fx.decision_response("Approve")])
        self.assertEqual(code, common._EXIT_OK)
        gate = last_gate(out)
        self.assertEqual(gate["context"]["items"][0]["stuck_wake"], "2")
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["stuck_wakes"], "2")

        t3 = t2 + datetime.timedelta(minutes=40)
        code, out = self.run_poll(now=t3, responses=[fx.decision_response("Approve")])
        self.assertEqual(code, common._EXIT_OK)
        gate = last_gate(out)
        self.assertEqual(gate["context"]["items"][0]["stuck_wake"], "3")
        self.assertEqual(self.fx.queue_rows()[0]["stuck_wakes"], "3")

    def test_stuck_max_exhausted_notifies_and_flags(self):
        self.fx.add_queue_row(**self.STUCK)
        rows = self.fx.queue_rows()
        rows[0]["stuck_wakes"] = "3"
        rows[0]["stuck_last_wake_at"] = "2026-10-07T12:00:00+00:00"  # FAKE_NOW
        fx.Fixture._write_csv(self.fx, self.fx.root / "data" / "review_queue.csv",
                              list(rows[0].keys()), rows)

        calls = []
        responses = [fx.decision_response("Approve"), fx.ok_post_response()]

        def side(method, url, payload=None, headers=None, timeout=30):
            if method == "POST":
                calls.append((method, url, payload or {}))
            return responses.pop(0)

        with mock.patch("m91_review.common.http_request", side_effect=side), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW + datetime.timedelta(minutes=40)):
            code, out = fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))  # exhausted item no longer wakes the agent
        row = self.fx.queue_rows()[0]
        self.assertEqual(row["needs_attention"], "yes")
        self.assertEqual(row["stuck_wakes"], "3")
        method, url, _ = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/v1/alerts"))
        self.assertIn("stuck", out.lower())

    def test_stuck_notice_uses_low_severity_and_dedup_id(self):
        self.fx.add_queue_row(**self.STUCK)
        rows = self.fx.queue_rows()
        rows[0]["stuck_wakes"] = "3"
        rows[0]["stuck_last_wake_at"] = "2026-10-07T12:00:00+00:00"
        fx.Fixture._write_csv(self.fx, self.fx.root / "data" / "review_queue.csv",
                              list(rows[0].keys()), rows)

        seen = {}

        def capture(method, url, payload=None, headers=None, timeout=30):
            if method == "POST":
                seen["payload"] = payload or {}
                return fx.ok_post_response()
            return fx.decision_response("Approve")

        with mock.patch("m91_review.common.http_request", side_effect=capture), \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW + datetime.timedelta(minutes=40)):
            code, _ = fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])
        self.assertEqual(code, common._EXIT_OK)
        payload = seen["payload"]
        self.assertEqual(payload["severity"], "LOW")
        self.assertEqual(payload["customId"], "blog-sys-stuck-p1-v1")
        self.assertIn("stuck", payload["description"].lower())
        self.assertTrue(payload["isAutoClose"])

    def test_stuck_needs_attention_no_wake_no_repeat_notice(self):
        self.fx.add_queue_row(**self.STUCK)
        rows = self.fx.queue_rows()
        rows[0]["stuck_wakes"] = "3"
        rows[0]["needs_attention"] = "yes"
        fx.Fixture._write_csv(self.fx, self.fx.root / "data" / "review_queue.csv",
                              list(rows[0].keys()), rows)
        with mock.patch("m91_review.common.http_request", side_effect=[fx.decision_response("Approve")]) as req, \
             mock.patch("m91_review.common.utc_now", return_value=FAKE_NOW + datetime.timedelta(minutes=40)):
            code, out = fx.run_capture(m91_review.cmd_poll, self.env, self.cfg, self.fx.root, [])
        self.assertEqual(code, common._EXIT_OK)
        self.assertFalse(json_wake(out))
        self.assertEqual(req.call_count, 1)  # only the decision read, no second notice POST
        self.assertEqual(self.fx.queue_rows()[0]["needs_attention"], "yes")


class TestSecretRedaction(ReviewTestBase):
    def test_secrets_never_printed(self):
        phone = self.env["M91_REVIEWER_PHONE"]
        key = self.env["M91_API_KEY"]
        common.register_secret(phone)
        common.register_secret(key)
        _, out = fx.run_capture(common.out, "inherited phone", phone, "key", key)
        self.assertNotIn(phone, out)
        self.assertNotIn(key, out)
        self.assertIn("***", out)


class TestNotifySystem(ReviewTestBase):
    def test_notify_sends_and_returns_0(self):
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response()):
            code = m91_review.main(["notify-system", "something", "failed"])
        self.assertEqual(code, common._EXIT_OK)

    def test_notify_zero_delivered_exits_3(self):
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response(delivered=0)):
            code = m91_review.main(["notify-system", "something", "failed"])
        self.assertEqual(code, common._EXIT_ZERO_DELIVERED)


LONG_TITLE = "How to Stop Your AI Agent From Spending $160 on Domains Without Asking"


class TestAlertFormat(ReviewTestBase):
    """Fixes 1-3: short 'Blog ready:' title, readable description, single draft
    path, whole-hours reminder, and the word-count warning."""

    def write_draft(self, title, name="test.md", words="Some body text for the post."):
        text = ("---\ntitle: %s\nmeta_description: m\nsummary: This is the summary.\n"
                "type: article\n---\n# H\n\n%s\n" % (title, words))
        (self.fx.root / "drafts" / name).write_text(text, encoding="utf-8")

    def raise_payload(self, **inv_overrides):
        self.fx.add_inventory(**inv_overrides)
        with mock.patch("m91_review.common.http_request", return_value=fx.ok_post_response()) as req:
            code = m91_review.main(["raise", "p1", "1"])
        self.assertEqual(code, common._EXIT_OK)
        return req.call_args[1]["payload"]

    def test_title_prefixed_and_truncated(self):
        self.write_draft(LONG_TITLE)
        payload = self.raise_payload(title=LONG_TITLE)
        self.assertTrue(payload["title"].startswith("Blog ready: "))
        short = payload["title"][len("Blog ready: "):]
        self.assertLessEqual(len(short), 48)
        self.assertTrue(short.endswith("…"))
        self.assertTrue(LONG_TITLE.startswith(short[:-1]))

    def test_short_title_under_cap_kept_full(self):
        self.write_draft("Short title")
        payload = self.raise_payload(title="Short title")
        self.assertEqual(payload["title"], "Blog ready: Short title")

    def test_description_lines_readable(self):
        payload = self.raise_payload()
        first = payload["description"].splitlines()[0]
        self.assertTrue(first.startswith("Topic group approvals ·"))
        for token in ("· human-in-the-loop ·", "· v1 ·", "· 8 words"):
            self.assertIn(token, first)
        self.assertIn("Read it in the chat or at drafts/test.md", payload["description"])
        self.assertNotIn("drafts/drafts", payload["description"])

    def test_reminder_whole_hours(self):
        payload = self.raise_payload()
        self.assertIn("Reminder after 6 hours.", payload["description"])
        self.assertNotIn("6.0", payload["description"])

    def test_word_count_warning_over_and_under(self):
        # fixture DRAFT body is 8 words -> UNDER target (min 1000)
        under = self.raise_payload()
        self.assertIn("Word count 8 is outside the target of 1000-1800 words.", under["description"])
        # a long draft -> OVER target (max 1800)
        big = "---\ntitle: Big post\n---\n# H\n\n" + " ".join(["w%d" % i for i in range(1900)]) + "\n"
        (self.fx.root / "drafts" / "big.md").write_text(big, encoding="utf-8")
        over = self.raise_payload(draft_path="drafts/big.md")
        self.assertIn("Word count 1902 is outside the target of 1000-1800 words.", over["description"])


class TestBodyWordCount(unittest.TestCase):
    def setUp(self):
        fx.reset_secrets()

    def test_excludes_front_matter(self):
        text = "---\ntitle: Ignored title words\n---\n# H\n\nSome body text for the post."
        self.assertEqual(common.body_word_count(text), 8)

    def test_excludes_check_results_section(self):
        text = ("---\ntitle: X\n---\n# H\n\nQuote the words here.\n\n"
                "## Check results\n\n- word count one two three four five six seven")
        self.assertEqual(common.body_word_count(text), 6)

    def test_draft_rel_single_prefix(self):
        self.assertEqual(common.draft_rel("drafts/a.md"), "drafts/a.md")
        self.assertEqual(common.draft_rel("a.md"), "drafts/a.md")
        self.assertEqual(common.draft_rel(r"drafts\a.md"), "drafts/a.md")
        self.assertEqual(common.draft_rel(""), "")

    def test_format_hours_no_trailing_zero(self):
        self.assertEqual(common.format_hours(6), "6")
        self.assertEqual(common.format_hours(6.0), "6")
        self.assertEqual(common.format_hours(6.5), "6.5")


class TestWordcountCommand(ReviewTestBase):
    def test_wordcount_under(self):
        code, out = fx.run_capture(m91_review.main, ["wordcount", "drafts/test.md"])
        self.assertEqual(code, common._EXIT_OK)
        self.assertIn("wordcount: 8", out)
        self.assertIn("target: 1000-1800", out)
        self.assertIn("status: UNDER", out)

    def test_wordcount_in_range(self):
        md = "---\ntitle: X\n---\n# H\n\n" + " ".join(["w%d" % i for i in range(1400)]) + "\n"
        (self.fx.root / "drafts" / "ok.md").write_text(md, encoding="utf-8")
        code, out = fx.run_capture(m91_review.main, ["wordcount", "drafts/ok.md"])
        self.assertEqual(code, common._EXIT_OK)
        self.assertIn("wordcount: 1402", out)
        self.assertIn("status: OK", out)

    def test_wordcount_over(self):
        md = "---\ntitle: X\n---\n# H\n\n" + " ".join(["w%d" % i for i in range(1900)]) + "\n"
        (self.fx.root / "drafts" / "big.md").write_text(md, encoding="utf-8")
        code, out = fx.run_capture(m91_review.main, ["wordcount", "drafts/big.md"])
        self.assertEqual(code, common._EXIT_OK)
        self.assertIn("wordcount: 1902", out)
        self.assertIn("status: OVER", out)


AUDIT_429 = [
    {"ts": "2026-10-07T10:05:00Z", "job_id": "writer", "fire_id": "f-new",
     "error": "RuntimeError: HTTP 429: Rate limit exceeded: free-models-per-day."},
    {"ts": "2026-10-07T09:00:00Z", "job_id": "strategist", "fire_id": "f-old",
     "error": "RuntimeError: HTTP 429: Rate limit exceeded: free-models-per-day."},
    {"ts": "2026-10-07T10:06:00Z", "job_id": "writer", "fire_id": "f-ok", "error": None},
    {"ts": "2026-10-07T10:07:00Z", "job_id": "writer", "fire_id": "f-other", "error": "RuntimeError: boom"},
]


class TestCron429Watchdog(ReviewTestBase):
    """Fix 5: a rate-limited cron run ends with a LOW notify-system, never
    silently — enforced by the poller watchdog reading the usage audit."""

    FAKE_NOW = datetime.datetime(2026, 10, 7, 10, 20, tzinfo=datetime.timezone.utc)

    def setUp(self):
        super().setUp()
        self.audit = self.fx.root / "usage_audit_test.jsonl"
        self.audit.write_text("\n".join(json.dumps(r) for r in AUDIT_429) + "\n", encoding="utf-8")
        self._old_audit = os.environ.get("M91_AUDIT_PATH")
        os.environ["M91_AUDIT_PATH"] = str(self.audit)

    def tearDown(self):
        if self._old_audit is None:
            os.environ.pop("M91_AUDIT_PATH", None)
        else:
            os.environ["M91_AUDIT_PATH"] = self._old_audit
        super().tearDown()

    def test_scan_filters_by_window_and_error(self):
        hits = m91_review.scan_audit_429s(self.fx.root, self.FAKE_NOW, window_minutes=20)
        self.assertEqual([h["fire_id"] for h in hits], ["f-new"])

    def test_notify_sends_once_low_autoclosed(self):
        calls = []

        def fake_send(env, cfg, phone, title, description, custom_id, severity,
                      response_options=None, is_auto_close=False):
            calls.append({"custom_id": custom_id, "severity": severity,
                          "description": description, "is_auto_close": is_auto_close})
            return {"_id": "x", "delivered": 1, "deduplicated": False}

        with mock.patch("m91_review.send_alert", side_effect=fake_send):
            m91_review._notify_cron_429s(self.env, self.cfg, self.fx.root, self.FAKE_NOW)
            m91_review._notify_cron_429s(self.env, self.cfg, self.fx.root, self.FAKE_NOW)
        self.assertEqual(len(calls), 1)  # deduplicated through the sent-state file
        self.assertEqual(calls[0]["custom_id"], "blog-sys-cron429-f-new")
        self.assertEqual(calls[0]["severity"], "LOW")
        self.assertTrue(calls[0]["is_auto_close"])
        self.assertIn("f-new", calls[0]["description"])
        self.assertNotIn("f-old", calls[0]["description"])
        state = (self.fx.root / "data" / "cron_429_sent.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(state).get("f-new"), "sent")

    def test_notify_without_env_records_gap_no_crash(self):
        with mock.patch("m91_review.send_alert") as sa:
            m91_review._notify_cron_429s({}, self.cfg, self.fx.root, self.FAKE_NOW)
        sa.assert_not_called()
        state = self.fx.root / "data" / "cron_429_sent.json"
        self.assertTrue(state.is_file())
        self.assertEqual(json.loads(state.read_text(encoding="utf-8")).get("f-new"),
                         "unnotified-missing-env")


if __name__ == "__main__":
    unittest.main()