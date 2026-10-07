# -*- coding: utf-8 -*-
"""Dry-run proof: Hermes --script wake gate for the decision poller.

Runs the REAL Hermes gate function (cron/scheduler_prompt._parse_wake_gate — the
verbatim function living in the installed hermes-agent) against the real stdout of
consecutive `m91_review.py poll` runs (M91 API mocked). This is exactly what the
cron scheduler evaluates each tick for a job with `--script m91_review.py`:

    cron/scheduler.py:2310   if _ran_ok and not _parse_wake_gate(_script_output)
    cron/scheduler.py:2319   -> return (True, silent_doc, SILENT_MARKER, None)  # no LLM, no delivery

Scenario A (fresh decision):  idle -> event -> idle -> idle  => wakes 0, 1, 0, 0.
  A hash-based --monitor-script would wake again on the event -> idle byte change;
  --script is content-based, so {"wakeAgent": false} always skips (no LLM call).

Scenario B (stuck row): a decided row not actioned within the grace (default 30
  min) is re-woken up to max_stuck_wakes (3), then a LOW notice is sent and the
  row is flagged needs_attention with no further agent wake.

The gate function is loaded by file path so no Hermes dependency stack is needed
(hermes_time and the sibling cron imports are stubbed at module load; the gate
body itself uses only the stdlib). Run with any python that has PyYAML:

    python scripts/tests/proof_wake_gate.py

Exit code 0 = both sequences proved; 1 = mismatch.
"""

import datetime
import importlib.util
import json
import os
import sys
import types
from unittest import mock

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(BASE, "tests")
for p in (TESTS_DIR, BASE):
    if p not in sys.path:
        sys.path.insert(0, p)

HERMES_AGENT = r"C:\Users\risha\AppData\Local\hermes\hermes-agent"

import fixtures as fx
import m91_review
import m91_common as common

FAKE_NOW = datetime.datetime(2026, 10, 7, 12, 0, tzinfo=datetime.timezone.utc)
APPROVE = fx.decision_response("Approve", note="looks good")


def load_real_gate():
    """Return cron.scheduler_prompt._parse_wake_gate from the installed hermes-agent."""
    ht = types.ModuleType("hermes_time")
    ht.now = lambda: datetime.datetime.now(datetime.timezone.utc)
    sys.modules["hermes_time"] = ht
    for name in ("cron", "cron.scheduler", "cron.scheduler_delivery", "cron.scheduler_script"):
        sys.modules[name] = types.ModuleType(name)
    path = os.path.join(HERMES_AGENT, "cron", "scheduler_prompt.py")
    spec = importlib.util.spec_from_file_location("scheduler_prompt_real", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._parse_wake_gate


_parse_wake_gate = load_real_gate()


class PollMockSideEffect:
    """Scripted responses consumed in call order, ignoring method/url."""

    def __init__(self, responses):
        self.q = list(responses)

    def __call__(self, method, url, payload=None, headers=None, timeout=30):
        return self.q.pop(0)


def last_gate_json(out):
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


def run_poll(env, cfg, root, responses, now=FAKE_NOW, posts=None):
    q = PollMockSideEffect(responses)  # one shared queue per poll tick

    def side(method, url, payload=None, headers=None, timeout=30):
        returned = q(method, url, payload=payload, headers=headers, timeout=timeout)
        if method == "POST" and posts is not None:
            posts.append((url, payload or {}, returned))
        return returned

    with mock.patch("m91_review.common.http_request", side_effect=side), \
         mock.patch("m91_review.common.utc_now", return_value=now):
        return fx.run_capture(m91_review.cmd_poll, env, cfg, root, [])


def print_header():
    print("=" * 78)
    print("Wake-gate dry run: real hermes-agent cron/scheduler_prompt._parse_wake_gate")
    print("against real m91_review.py poll stdout (M91 API mocked).")
    print("=" * 78)
    print("%-26s %-38s %-9s %-9s %s" % ("poll tick", "last stdout line", "Hermes", "agent", "note"))
    print("-" * 78)


def scenario_a():
    print_header()
    f = fx.Fixture()
    env = fx.make_env()
    cfg = common.load_config(f.root / "config.yaml")
    f.add_inventory()
    f.add_queue_row()

    steps = []
    _, out = run_poll(env, cfg, f.root, [fx.no_decision_response()])
    steps.append(("1 idle (nothing new)", out, False, ""))
    _, out = run_poll(env, cfg, f.root, [APPROVE, fx.close_response(), fx.close_response()])
    steps.append(("2 decision event", out, True, "decided by main"))
    _, out = run_poll(env, cfg, f.root, [APPROVE])
    steps.append(("3 idle (post-event)", out, False, "decision already recorded"))
    _, out = run_poll(env, cfg, f.root, [APPROVE])
    steps.append(("4 idle (stable)", out, False, ""))

    ok = True
    vector = []
    for label, out, expected, note in steps:
        gate = last_gate_json(out)
        gates = json.dumps(gate) if gate else repr(None)
        wakes = _parse_wake_gate(out)
        vector.append(1 if wakes else 0)
        tag = "" if wakes == expected else "  <-- MISMATCH"
        print("%-26s %-38s %-9s %-9s %s%s" % (label, gates[:38], str(wakes),
                                               "yes" if wakes else "no", note, tag))
        ok = ok and wakes == expected
    print("-" * 78)
    print("wake vector: %s  expected [0, 1, 0, 0]  -> %s" % (vector, "OK" if vector == [0, 1, 0, 0] else "FAIL"))
    row = f.queue_rows()[0]
    print("queue state: decision=%r decided_by=%r status=%r" %
          (row.get("decision"), row.get("decided_by"), row.get("status")))
    print("")
    return ok and vector == [0, 1, 0, 0]


def scenario_b():
    print_header()
    f = fx.Fixture()
    env = fx.make_env()
    cfg = common.load_config(f.root / "config.yaml")
    f.add_inventory()
    f.add_queue_row(decision="Approve", decided_by="main",
                    decided_at=(FAKE_NOW - datetime.timedelta(minutes=40)).isoformat(timespec="seconds"))
    posts = []

    ticks = [
        # (label, now delta, responses, expected wake, note)
        ("1 decision, un-actioned 40m", datetime.timedelta(0), [APPROVE], True, "stuck wake 1 of 3"),
        ("2 10m later (grace)", datetime.timedelta(minutes=10), [APPROVE], False, "inside 30m grace"),
        ("3 35m after wake 1", datetime.timedelta(minutes=45), [APPROVE], True, "stuck wake 2 of 3"),
        ("4 10m later (grace)", datetime.timedelta(minutes=55), [APPROVE], False, "inside 30m grace"),
        ("5 40m after wake 2", datetime.timedelta(minutes=95), [APPROVE], True, "stuck wake 3 of 3"),
        ("6 40m after wake 3", datetime.timedelta(minutes=135), [APPROVE, fx.ok_post_response()], False,
         "LOW notice sent, needs_attention"),
    ]

    ok = True
    vector = []
    for label, delta, responses, expected, note in ticks:
        code, out = run_poll(env, cfg, f.root, responses, now=FAKE_NOW + delta, posts=posts)
        gate = last_gate_json(out)
        gates = json.dumps(gate) if gate else repr(None)
        wakes = _parse_wake_gate(out)
        vector.append(1 if wakes else 0)
        tag = "" if wakes == expected else "  <-- MISMATCH"
        print("%-26s %-38s %-9s %-9s %s%s" % (label, gates[:38], str(wakes),
                                               "yes" if wakes else "no", note, tag))
        ok = ok and wakes == expected
    print("-" * 78)
    print("wake vector: %s  expected [1, 0, 1, 0, 1, 0]  -> %s" % (vector, "OK" if vector == [1, 0, 1, 0, 1, 0] else "FAIL"))
    row = f.queue_rows()[0]
    flagged = row.get("needs_attention") == "yes"
    print("queue state: decision=%r stuck_wakes=%s needs_attention=%r status=%r" %
          (row.get("decision"), row.get("stuck_wakes"), row.get("needs_attention"), row.get("status")))
    print("stuck LOW notices POSTed: %d (flag set: %s)" % (len(posts), flagged))
    print("")
    return ok and vector == [1, 0, 1, 0, 1, 0] and len(posts) == 1 and flagged


def main():
    fx.reset_secrets()
    a = scenario_a()
    b = scenario_b()
    print("=" * 78)
    print("Scenario A (idle -> event -> idle -> idle   [0, 1, 0, 0]): %s" % ("PASS" if a else "FAIL"))
    print("Scenario B (stuck re-wakes then LOW notice  [1,0,1,0,1,0]): %s" % ("PASS" if b else "FAIL"))
    print("=" * 78)
    return 0 if (a and b) else 1


if __name__ == "__main__":
    sys.exit(main())