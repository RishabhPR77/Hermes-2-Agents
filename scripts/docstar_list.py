"""docstar_list.py — list posts already on Docstar (duplicate-slug check).

Reads the viaSocket list flow. Prints one line per post:

    <slug> | <title> | <url> | <updated>

Used by docstar_publish.py to refuse duplicate slugs.

Exit codes:
    0 success (empty list is success, exit 0)
    1 bad usage
    4 missing environment variable
    6 viaSocket / Docstar unreachable or error envelope
"""

import json
import os
import sys

import m91_common as common


def list_posts(env, cfg):
    common.require_env(env, "VIASOCKET_LIST_WEBHOOK", "VIASOCKET_SHARED_SECRET")
    webhook = env["VIASOCKET_LIST_WEBHOOK"]
    payload = {"action": "list"}
    parent = common.cfg_get(cfg, "publish", "parent", default="")
    if parent:
        payload["parent"] = parent
    headers = {"X-ViaSocket-Secret": env["VIASOCKET_SHARED_SECRET"]}
    if os.environ.get("DOCSTAR_DRY_RUN"):
        common.out("DRY-RUN list", webhook, common.redact(json.dumps(payload, ensure_ascii=False)))
        return []
    status, envelope = common.http_request("POST", webhook, payload=payload, headers=headers)
    if status != 200:
        code, message = common.error_of(envelope)
        raise common.ApiError(status, code, "viaSocket list failed: %s" % message)
    data = common.data_of(envelope)
    if data is None:
        return []
    posts = data if isinstance(data, list) else data.get("posts", [])
    return posts if isinstance(posts, list) else []


def cmd_list(env, cfg, root, args):
    posts = list_posts(env, cfg)
    for p in posts:
        if not isinstance(p, dict):
            continue
        common.out("%s | %s | %s | %s" % (
            p.get("slug", ""), p.get("title", ""),
            p.get("url", ""), p.get("updated", "")))
    common.out("Total: %d posts" % len(posts))
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
        return cmd_list(env, cfg, root, argv)
    except common.UsageError as e:
        common.err("docstar_list: %s" % e)
        return common._EXIT_USAGE
    except common.EnvError as e:
        common.err("docstar_list: %s" % e)
        return common._EXIT_ENV
    except (common.ApiError, common.NetworkError) as e:
        common.err("docstar_list: %s" % e)
        return common._EXIT_DOCSTAR


if __name__ == "__main__":
    sys.exit(main())