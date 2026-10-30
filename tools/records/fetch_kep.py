"""#3 Kubernetes enhancement proposals: the kubernetes/enhancements repository (Apache-2.0), pinned to the current commit
of its default branch (one GitHub API request), stored as the unmodified codeload tarball.

    python -I tools/records/fetch_kep.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "kep"
REPO = "kubernetes/enhancements"
LICENCE = {"name": "Apache-2.0", "url": "https://github.com/kubernetes/enhancements/blob/master/LICENSE"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    meta = json.load(open(R.fetch_file(DOMAIN, a.snapshot, f"https://api.github.com/repos/{REPO}/commits/HEAD",
                                       "enhancements.head.json", headers={"Accept": "application/vnd.github+json"})))
    sha = meta["sha"]
    R.fetch_file(DOMAIN, a.snapshot, f"https://codeload.github.com/{REPO}/tar.gz/{sha}", f"enhancements-{sha[:12]}.tar.gz")
    print(f"{REPO} @ {sha}")
    log = json.load(open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")))
    log["licence"] = dict(LICENCE, url=f"https://github.com/{REPO}/blob/{sha}/LICENSE")
    json.dump(log, open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json"), "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
