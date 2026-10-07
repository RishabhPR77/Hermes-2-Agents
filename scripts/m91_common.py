"""m91_common — shared helpers for the M91 blog deterministic scripts.

No third-party dependencies. Everything here is stdlib. Secrets (API key,
phones, webhook URLs, shared secret) are registered for redaction the moment
they are read and are never written to any file, log or stdout.
"""

import csv
import datetime
import json
import os
import pathlib
import re
import ssl
import sys
import urllib.error
import urllib.request

try:
    import yaml as _yaml
except Exception:  # pragma: no cover - pyyaml normally present
    _yaml = None

ENV_NAMES = (
    "M91_API_KEY",
    "M91_REVIEWER_PHONE",
    "M91_BACKUP_REVIEWER_PHONE",
    "VIASOCKET_PUBLISH_WEBHOOK",
    "VIASOCKET_LIST_WEBHOOK",
    "VIASOCKET_SHARED_SECRET",
)

DEFAULT_API_BASE = "https://siren-backend-1091285226236.asia-south1.run.app"

_EXIT_OK = 0
_EXIT_USAGE = 1
_EXIT_API = 2
_EXIT_ZERO_DELIVERED = 3
_EXIT_ENV = 4
_EXIT_POLL_ALL_FAILED = 5
_EXIT_DOCSTAR = 6
_EXIT_UNAPPROVED = 7
_EXIT_DUPLICATE_SLUG = 8
_EXIT_ALREADY_PUBLISHED = 9


class ApiError(Exception):
    """M91 API returned a status we treat as an error."""

    def __init__(self, status, code=None, message=None):
        self.status = status
        self.code = code or "HTTP %s" % status
        self.message = (message or "").strip()
        super().__init__(redact(str(self.code) + ((" - " + str(self.message)) if self.message else "")))


class NetworkError(Exception):
    """M91 / viaSocket could not be reached at all."""


class UsageError(Exception):
    pass


class EnvError(Exception):
    pass


# --------------------------------------------------------------------------- secrets
_SECRETS = []


def register_secret(value):
    v = str(value or "")
    if v and v not in _SECRETS:
        _SECRETS.append(v)


def redact(text):
    """Mask every registered secret appearing anywhere in text."""
    out = str(text)
    for v in sorted(_SECRETS, key=len, reverse=True):
        out = out.replace(v, "***")
    return out


def out(*parts):
    print(redact(" ".join(str(p) for p in parts)))


def err(*parts):
    print(redact(" ".join(str(p) for p in parts)), file=sys.stderr)


# --------------------------------------------------------------------------- env
def load_env():
    """Read the passthrough variables, registering each as a secret.

    Returns a dict of {NAME: value}. Missing names are not errors here; the
    commands that need them check individually (exit code 4).
    """
    env = {}
    for name in ENV_NAMES:
        value = os.environ.get(name, "")
        if value:
            env[name] = value
            register_secret(value)
    return env


def require_env(env, *names):
    for name in names:
        if not env.get(name):
            raise EnvError("missing environment variable %s (see .env.example)" % name)


def api_base(env):
    return os.environ.get("M91_API", DEFAULT_API_BASE).rstrip("/")


# --------------------------------------------------------------------------- project / config
def project_root():
    override = os.environ.get("M91_BLOG_ROOT")
    if override:
        return pathlib.Path(override)
    candidates = [pathlib.Path.cwd()]
    candidates.append(pathlib.Path(__file__).resolve().parent.parent)
    candidates.append(pathlib.Path(__file__).resolve().parent)
    for c in candidates:
        if (c / "config.yaml").exists() and (c / "data").is_dir():
            return c
    return pathlib.Path.cwd()


def cfg_get(cfg, *keys, default=None):
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def load_config(path=None):
    p = pathlib.Path(path) if path else (project_root() / "config.yaml")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        raise EnvError("config.yaml not found at %s" % p)
    if _yaml is not None:
        data = _yaml.safe_load(text) or {}
    else:
        data = _mini_yaml(text)
    if not isinstance(data, dict):
        data = {}
    return data


def _mini_yaml(text):
    """Fallback YAML-subset parser (nested maps + scalars). Only used when
    PyYAML is unavailable; the project config.yaml is small and known."""

    def scalar(s):
        s = s.strip()
        if not s:
            return None
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        if s in ("true", "True"):
            return True
        if s in ("false", "False"):
            return False
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d+", s):
            return float(s)
        if s.startswith("[") and s.endswith("]"):
            return [x.strip().strip('"').strip("'") for x in s[1:-1].split(",") if x.strip()]
        return s

    lines = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append(line)

    def block(i, indent):
        obj = {}
        while i < len(lines):
            line = lines[i]
            cur = len(line) - len(line.lstrip(" "))
            if cur < indent:
                break
            content = line.strip()
            if cur > indent or ":" not in content:
                i += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip('"').strip("'")
            rest = rest.strip()
            if rest:
                obj[key] = scalar(rest)
                i += 1
                continue
            j = i + 1
            if j < len(lines):
                child_indent = len(lines[j]) - len(lines[j].lstrip(" "))
                nested, j = block(j, child_indent)
                obj[key] = nested
            else:
                obj[key] = None
            i = j
        return obj, i

    data, _ = block(0, 0)
    return data


# --------------------------------------------------------------------------- time
def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def now_iso():
    return utc_now().isoformat(timespec="seconds")


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def deadline_from(start, hours):
    return (start + datetime.timedelta(hours=float(hours))).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- csv
def csv_fields(path, default):
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            first = f.readline().strip()
        if first:
            return [c.strip() for c in first.split(",")]
    return default


def read_rows(path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def append_rows(path, rows, fields):
    existing = read_rows(path)
    existing.extend(rows)
    write_rows(path, existing, fields)


def row_matches(row, **kw):
    for k, v in kw.items():
        if str(row.get(k, "")).strip() != str(v):
            return False
    return True


def load_inventory(root):
    path = root / "data" / "content_inventory.csv"
    return {r["id"]: r for r in read_rows(path) if r.get("id")}


def load_queue(root):
    path = root / "data" / "review_queue.csv"
    return read_rows(path)


def load_keyword_bank(root):
    return read_rows(root / "data" / "keyword_bank.csv")


# --------------------------------------------------------------------------- http
def http_request(method, url, payload=None, headers=None, timeout=30):
    """Low-level call. Returns (status_code, parsed_json_envelope_or_dict)."""
    req = urllib.request.Request(url, method=method, headers=dict(headers or {}))
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, body, timeout=timeout, context=ctx) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = ""
        if e.fp:
            try:
                raw = e.fp.read().decode("utf-8", "replace")
            except Exception:
                raw = ""
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise NetworkError(redact(str(e)))
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except ValueError:
        parsed = {}
    return status, parsed


def data_of(envelope):
    if isinstance(envelope, dict) and envelope.get("success") and isinstance(envelope.get("data"), (dict, list)):
        return envelope["data"]
    return None


def error_of(envelope):
    if isinstance(envelope, dict):
        e = envelope.get("error") or {}
        if isinstance(e, dict):
            return e.get("code"), e.get("message") or e.get("docs") or ""
    return None, ""


# --------------------------------------------------------------------------- text helpers
def split_front_matter(text):
    """Return (front_matter_dict, body_text) for a markdown draft."""
    if text.startswith("---\n") or text.startswith("---\r\n"):
        lines = text.splitlines(keepends=True)
        acc = []
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            acc.append(lines[i])
            i += 1
        fm = {}
        for line in acc:
            line = line.split("#", 1)[0].rstrip("\r\n")
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            elif v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif re.fullmatch(r"-?\d+", v):
                v = int(v)
            fm[k] = v
        body = "".join(lines[i + 1:]) if i < len(lines) else ""
        return fm, body
    return {}, text


def word_count(text):
    return len(re.findall(r"\S+", text.strip()))


def body_word_count(text):
    """Count the words of the publishable body of a draft.

    Excludes the YAML front matter and the trailing "Check results" section
    the Writer appends, so the Writer's trim check and the review-alert
    warning always agree on one number.
    """
    _, body = split_front_matter(text)
    cut = re.search(r"(?im)^\s*#{1,6}\s*check\s+results\s*$", body)
    if cut:
        body = body[: cut.start()]
    return word_count(body)


def format_hours(hours):
    """'6' for 6.0, '6.5' for 6.5 — no trailing ".0" in alert copy."""
    return "%g" % float(hours)


def draft_rel(path):
    """Normalise a draft path to 'drafts/<name>' with a single prefix."""
    s = (path or "").replace("\\", "/").strip()
    if not s:
        return ""
    if s.startswith("drafts/"):
        return s
    return "drafts/" + s


def truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 3] + "..."


def markdown_to_html(md):
    """Minimal deterministic markdown -> HTML used for the Docstar payload."""
    lines = md.splitlines(keepends=True)
    out = []
    i = 0
    in_code = False
    code_buf = []
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\r\n")
        if stripped.startswith("```"):
            if in_code:
                code = "".join(code_buf).rstrip()
                out.append("<pre><code>" + _html_escape(code) + "</code></pre>")
                in_code = False
                code_buf = []
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(stripped + "\n")
            i += 1
            continue
        if not stripped.strip():
            i += 1
            continue
        if re.match(r"^#{1,6} ", stripped):
            level = len(re.match(r"^#{1,6}", stripped).group(0))
            out.append("<h%d>%s</h%d>" % (level, _inline(stripped[level + 1:]), level))
        elif re.match(r"^>\s?", stripped):
            quote = re.sub(r"^>\s?", "", stripped)
            out.append("<blockquote>" + _inline(quote) + "</blockquote>")
        elif re.match(r"^\s*[-*] ", stripped):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i].rstrip("\r\n")):
                items.append("<li>" + _inline(re.sub(r"^\s*[-*] ", "", lines[i].rstrip("\r\n"))) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif re.match(r"^\s*\d+\. ", stripped):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\. ", lines[i].rstrip("\r\n")):
                items.append("<li>" + _inline(re.sub(r"^\s*\d+\.\s*", "", lines[i].rstrip("\r\n"))) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        elif stripped.replace("|", "").strip() and "|" in stripped:
            cols = [] if not re.match(r"^\s*\|?\s*:?-+:?\s*\|?\s*$", stripped) else None
            if cols is not None:
                i += 1
            continue
        else:
            out.append("<p>" + _inline(stripped) + "</p>")
        i += 1
    if in_code:
        out.append("<pre><code>" + _html_escape("".join(code_buf).rstrip()) + "</code></pre>")
    return "\n".join(out)


def _html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _inline(s):
    s = _html_escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="nofollow">\1</a>', s)
    return s


def read_draft_text(root, draft_path):
    p = pathlib.Path(draft_path)
    if not p.is_absolute():
        p = root / p
    return p.read_text(encoding="utf-8")