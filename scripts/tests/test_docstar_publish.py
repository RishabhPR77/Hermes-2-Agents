# -*- coding: utf-8 -*-
"""Unit tests for docstar_publish.py refusal rules and happy path (mocked).

Cases:
  - unapproved publish refused -> exit 7
  - duplicate slug refused -> exit 8
  - already published -> exit 9 (no-op)
  - approved publish succeeds, updates inventory + queue, dry-run safe
"""

import os
import unittest
from unittest import mock

import fixtures as fx
import m91_common as common


class PublishTestBase(unittest.TestCase):
    def setUp(self):
        fx.reset_secrets()
        self.fx = fx.Fixture()
        self.addCleanup(self.fx.cleanup)
        self.env = fx.make_env()
        self.env["VIASOCKET_PUBLISH_WEBHOOK"] = "https://viasocket.example/publish"
        self.env["VIASOCKET_LIST_WEBHOOK"] = "https://viasocket.example/list"
        self.env["VIASOCKET_SHARED_SECRET"] = "shh-context"
        os.environ.update(self.env)
        os.environ["M91_BLOG_ROOT"] = str(self.fx.root)

    def tearDown(self):
        for k in ("M91_BLOG_ROOT", "M91_API_KEY", "M91_REVIEWER_PHONE",
                  "M91_BACKUP_REVIEWER_PHONE", "VIASOCKET_PUBLISH_WEBHOOK",
                  "VIASOCKET_LIST_WEBHOOK", "VIASOCKET_SHARED_SECRET"):
            os.environ.pop(k, None)

    def _approve(self):
        self.fx.add_inventory()
        self.fx.add_queue_row(decision="Approve", decided_by="main",
                              decided_at="2026-10-06T08:00:00+00:00")


class TestRefusals(PublishTestBase):
    def test_unapproved_refused_exit_7(self):
        self.fx.add_inventory()
        self.fx.add_queue_row()  # no decision
        with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]):
            code = docstar_publish_main(["p1", "1"])
        self.assertEqual(code, common._EXIT_UNAPPROVED)

    def test_reject_is_not_approval_exit_7(self):
        self.fx.add_inventory()
        self.fx.add_queue_row(decision="Reject", decided_by="main",
                              decided_at="2026-10-06T08:00:00+00:00")
        with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]):
            code = docstar_publish_main(["p1", "1"])
        self.assertEqual(code, common._EXIT_UNAPPROVED)

    def test_duplicate_slug_refused_exit_8(self):
        self._approve()
        with mock.patch("docstar_publish.docstar_list.list_posts",
                        return_value=[{"slug": "m91-human-in-the-loop-approvals",
                                       "title": "dup", "url": "x", "updated": "2026-10-01"}]):
            code = docstar_publish_main(["p1", "1"])
        self.assertEqual(code, common._EXIT_DUPLICATE_SLUG)

    def test_already_published_exit_9(self):
        self.fx.add_inventory(status="published", live_url="https://docstar.in/x")
        self.fx.add_queue_row(decision="Approve", decided_by="main",
                              decided_at="2026-10-06T08:00:00+00:00",
                              custom_id="blog-2026-10-06-m91-human-in-the-loop-approvals-v1")
        with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]):
            code = docstar_publish_main(["p1", "1"])
        self.assertEqual(code, common._EXIT_ALREADY_PUBLISHED)

    def test_unknown_post_exit_1(self):
        code = docstar_publish_main(["ghost", "1"])
        self.assertEqual(code, common._EXIT_USAGE)


class TestPublish(PublishTestBase):
    def test_approved_publish_succeeds_and_updates_state(self):
        self._approve()
        create_ok = (200, {"success": True, "data": {"url": "https://docstar.in/m91-approvals"}})
        with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]), \
             mock.patch("m91_common.http_request", return_value=create_ok) as req:
            code, out = fx.run_capture(docstar_publish_main, ["p1", "1"])
        self.assertEqual(code, common._EXIT_OK)
        self.assertIn("published", out)
        payload = req.call_args[1]["payload"]
        self.assertEqual(payload["action"], "create")
        self.assertEqual(payload["slug"], "m91-human-in-the-loop-approvals")
        self.assertEqual(payload["mode"], "draft")
        self.assertIn("<h1>Heading</h1>", payload["content_html"])
        self.assertIn("<p>Some body text for the post.</p>", payload["content_html"])
        posts = common.load_inventory(self.fx.root)
        self.assertEqual(posts["p1"]["status"], "published")
        self.assertEqual(posts["p1"]["live_url"], "https://docstar.in/m91-approvals")
        rows = self.fx.queue_rows()
        self.assertTrue(all(r["status"] == "published" for r in rows))
        self.assertTrue((self.fx.root / "ready" / "2026-10-06-m91-human-in-the-loop-approvals" / "post.md").is_file())

    def test_dry_run_skips_post_but_enforces_refusal(self):
        self.fx.add_inventory()
        self.fx.add_queue_row()
        os.environ["DOCSTAR_DRY_RUN"] = "1"
        try:
            with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]):
                code = docstar_publish_main(["p1", "1"])
            self.assertEqual(code, common._EXIT_UNAPPROVED)
        finally:
            os.environ.pop("DOCSTAR_DRY_RUN", None)

    def test_dry_run_approved_print_only(self):
        self._approve()
        os.environ["DOCSTAR_DRY_RUN"] = "1"
        try:
            with mock.patch("docstar_publish.docstar_list.list_posts", return_value=[]), \
                 mock.patch("m91_common.http_request") as req:
                code, out = fx.run_capture(docstar_publish_main, ["p1", "1"])
            self.assertEqual(code, common._EXIT_OK)
            req.assert_not_called()
            self.assertIn("DRY-RUN create", out)
        finally:
            os.environ.pop("DOCSTAR_DRY_RUN", None)


def docstar_publish_main(args):
    import docstar_publish
    return docstar_publish.main(args)


if __name__ == "__main__":
    unittest.main()