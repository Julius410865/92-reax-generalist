"""#4 Apache Software Foundation podlings: the projects.apache.org JSON files podlings-history.json (podlings that left the
Incubator: graduated or retired) and podlings.json (podlings still incubating), plus their upstream, the Incubator's
podlings.xml in the ASF Subversion repository (Apache-2.0), stored unmodified.

    python -I tools/records/fetch_asf_podling.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "asf_podling"
FILES = {"podlings-history.json": "https://projects.apache.org/json/foundation/podlings-history.json",
         "podlings.json": "https://projects.apache.org/json/foundation/podlings.json",
         "podlings.xml": "https://svn.apache.org/repos/asf/incubator/public/trunk/content/podlings.xml"}
LICENCE = {"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0",
           "note": "ASF project metadata: projects.apache.org JSON (generated from the Incubator's podlings.xml, whose header "
                   "states the Apache License 2.0)"}
PAUSE_S = 1.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    for name, url in FILES.items():
        R.fetch_file(DOMAIN, a.snapshot, url, name)
        time.sleep(PAUSE_S)
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    json.dump(log, open(path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
