"""#2 Rust RFCs: the pull requests of rust-lang/rfcs (MIT OR Apache-2.0), listed by the GitHub REST API pull list
(state=all, oldest first so that pages do not shift while paging, 100 per page), every page stored unmodified; plus the
repository tarball at the pinned commit of the default branch (the accepted RFC texts under text/, a second source for
the outcome).

    python -I tools/records/fetch_rust_rfc.py [--snapshot 2026-10-27] [--max-requests 40]

GitHub allows 60 unauthenticated API requests per hour per IP, shared with the other workers on the machine: at most
``--max-requests`` API requests are made (failed ones included). On 403 / 429 the script waits until the limit resets and
resumes; pages already stored are skipped, so a rerun continues where it stopped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "rust_rfc"
REPO = "rust-lang/rfcs"
PER_PAGE = 100
PULLS = f"https://api.github.com/repos/{REPO}/pulls?state=all&sort=created&direction=asc&per_page={PER_PAGE}&page={{page}}"
LICENCE_NOTE = ("README: the repository is 'in the process of being licensed under either of' Apache-2.0 or MIT 'at your "
                "option. Some parts of the repository are already licensed according to those terms' (RFC 2044). The pull "
                "request titles and bodies used here are GitHub metadata of the repository.")
API_HEADERS = {"Accept": "application/vnd.github+json"}
MIN_WAIT, MAX_WAIT = 60, 3700


class Budget:
    def __init__(self, cap: int):
        self.cap, self.used = cap, 0

    def api(self, url: str, name: str) -> str:
        """fetch_file for one api.github.com URL: counted, and on 403 / 429 a wait until the reset time, then a retry."""
        log = os.path.join(R.raw_dir(DOMAIN, self.snapshot), "fetch.json")
        if os.path.exists(log) and name in json.load(open(log))["files"] and \
                os.path.exists(os.path.join(R.raw_dir(DOMAIN, self.snapshot), name)):
            return R.fetch_file(DOMAIN, self.snapshot, url, name, headers=API_HEADERS)     # already stored: no request
        while True:
            if self.used >= self.cap:
                raise SystemExit(f"API request cap of {self.cap} reached before {name}; rerun later to resume")
            self.used += 1
            try:
                return R.fetch_file(DOMAIN, self.snapshot, url, name, headers=API_HEADERS)
            except urllib.error.HTTPError as exc:
                if exc.code not in (403, 429):
                    print(f"  {exc.code} on {name}: {exc.read()[:300]!r}", flush=True)
                    raise
                now = time.time()
                reset = exc.headers.get("x-ratelimit-reset")
                after = exc.headers.get("retry-after")
                wait = float(after) if after else (float(reset) - now + 5 if reset else MIN_WAIT)
                wait = min(max(wait, MIN_WAIT), MAX_WAIT)
                print(f"  {exc.code} on {name} (remaining {exc.headers.get('x-ratelimit-remaining')}); waiting {wait:.0f} s",
                      flush=True)
                time.sleep(wait)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    ap.add_argument("--max-requests", type=int, default=40)
    a = ap.parse_args(argv)
    b = Budget(a.max_requests)
    b.snapshot = a.snapshot
    meta = json.load(open(b.api(f"https://api.github.com/repos/{REPO}/commits/HEAD", "rfcs.head.json")))
    sha = meta["sha"]
    R.fetch_file(DOMAIN, a.snapshot, f"https://codeload.github.com/{REPO}/tar.gz/{sha}", f"rfcs-{sha[:12]}.tar.gz")
    print(f"{REPO} @ {sha}", flush=True)
    page, prs = 1, 0
    while True:
        path = b.api(PULLS.format(page=page), f"pulls/page-{page:03d}.json")
        items = json.load(open(path))
        if not isinstance(items, list):
            raise SystemExit(f"page {page}: not a list")
        prs += len(items)
        print(f"  page {page}: {len(items)} pull requests ({b.used} API requests so far)", flush=True)
        if len(items) < PER_PAGE:
            break
        page += 1
    d = R.raw_dir(DOMAIN, a.snapshot)
    log = json.load(open(os.path.join(d, "fetch.json")))
    log["licence"] = {"name": "MIT OR Apache-2.0", "url": f"https://github.com/{REPO}/blob/{sha}/README.md#license",
                      "files": [f"https://github.com/{REPO}/blob/{sha}/LICENSE-MIT",
                                f"https://github.com/{REPO}/blob/{sha}/LICENSE-APACHE"], "note": LICENCE_NOTE}
    log["pull_pages"] = page
    json.dump(log, open(os.path.join(d, "fetch.json"), "w"), indent=1)
    total = sum(f["bytes"] for f in log["files"].values())
    print(f"{prs} pull requests on {page} pages; {b.used} API requests this run; {total} bytes stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
