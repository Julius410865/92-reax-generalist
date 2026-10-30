"""#1 Ethereum improvement proposals: the ethereum/EIPs and ethereum/ERCs repositories (CC0-1.0), pinned to their current
commit, stored as the unmodified GitHub tarballs.

    python tools/records/fetch_eip.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "eip"
REPOS = ("ethereum/EIPs", "ethereum/ERCs")
LICENCE = {"name": "CC0-1.0", "url": "https://github.com/ethereum/EIPs/blob/master/LICENSE.md"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    for repo in REPOS:
        name = repo.split("/")[1]
        meta = json.load(open(R.fetch_file(DOMAIN, a.snapshot, f"https://api.github.com/repos/{repo}/commits/master",
                                           f"{name}.head.json", headers={"Accept": "application/vnd.github+json"})))
        sha = meta["sha"]
        R.fetch_file(DOMAIN, a.snapshot, f"https://codeload.github.com/{repo}/tar.gz/{sha}", f"{name}-{sha[:12]}.tar.gz")
        print(f"{repo} @ {sha}")
    log = json.load(open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")))
    log["licence"] = LICENCE
    json.dump(log, open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json"), "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
