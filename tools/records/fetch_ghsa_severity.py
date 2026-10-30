"""#9 Package security advisories: the github/advisory-database repository (CC BY 4.0), pinned to the current commit of
its default branch (one GitHub API request), stored as the unmodified codeload tarball (the build reads only the
advisories/github-reviewed tree of it).

    python -I tools/records/fetch_ghsa_severity.py [--snapshot 2026-10-27]

Size guards: the download must stay below MAX_DOWNLOAD and leave at least MIN_FREE on the disk. codeload sends no
Content-Length, so the process address space is capped (RLIMIT_AS): a larger response fails inside the read with a
MemoryError and nothing is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import resource
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ghsa_severity"
REPO = "github/advisory-database"
LICENCE = {"name": "CC-BY-4.0", "url": "https://github.com/github/advisory-database/blob/main/LICENSE.md",
           "attribution": "GitHub Advisory Database (github/advisory-database), CC BY 4.0"}
GB = 1024 ** 3
MAX_DOWNLOAD, MIN_FREE = 3 * GB, 40 * GB
ADDRESS_SPACE = int(3.5 * GB)    # the read holds the body twice at its end (chunks + join): bodies over ~1.7 GB fail too


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free = shutil.disk_usage(R.RAW if os.path.exists(R.RAW) else "/").free
    if free - MAX_DOWNLOAD < MIN_FREE:
        raise SystemExit(f"only {free / GB:.1f} GB free: a {MAX_DOWNLOAD / GB:.0f} GB download would leave under "
                         f"{MIN_FREE / GB:.0f} GB; stopping")
    meta = json.load(open(R.fetch_file(DOMAIN, a.snapshot, f"https://api.github.com/repos/{REPO}/commits/HEAD",
                                       "advisory-database.head.json", headers={"Accept": "application/vnd.github+json"})))
    sha = meta["sha"]
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, resource.getrlimit(resource.RLIMIT_AS)[1]))
    R.fetch_file(DOMAIN, a.snapshot, f"https://codeload.github.com/{REPO}/tar.gz/{sha}",
                 f"advisory-database-{sha[:12]}.tar.gz", timeout=1800)
    print(f"{REPO} @ {sha}")
    log = json.load(open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")))
    log["licence"] = dict(LICENCE, url=f"https://github.com/{REPO}/blob/{sha}/LICENSE.md")
    json.dump(log, open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json"), "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    print(f"free after download: {shutil.disk_usage(R.RAW).free / GB:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
