#!/usr/bin/env python3
"""Canary for the Cursor Teams source: fail loudly if any cost field is null.

Cursor returns fractional cents (e.g. spendCents: 9445.474115). If a schema,
destination, or API change ever turns these into nulls or integers, spend
reporting silently breaks. This script calls the live API and exits 1 with a
clear message if any cost field is null, missing, or non numeric.

Usage: CURSOR_API_KEY=crsr_... python3 canary/cost_field_canary.py
"""

import base64
import json
import os
import sys
import time
import urllib.request

BASE = "https://api.cursor.com"

# Fields that must be present and numeric on every record.
SPEND_REQUIRED = ["spendCents", "includedSpendCents"]
EVENT_REQUIRED = ["chargedCents", "requestsCosts"]
# Present only on some records (e.g. cursorTokenFee applies to third party
# models only), but when present must be numeric, never null.
EVENT_OPTIONAL = ["cursorTokenFee"]


def call(path, body=None):
    key = os.environ["CURSOR_API_KEY"]
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def check(records, required, optional, label):
    failures = []
    for r in records:
        for f in required:
            if not isinstance(r.get(f), (int, float)) or isinstance(r.get(f), bool):
                failures.append(f"{label}.{f} = {r.get(f)!r} (record: {r.get('email') or r.get('userEmail')})")
        for f in optional:
            if f in r and (not isinstance(r[f], (int, float)) or isinstance(r[f], bool)):
                failures.append(f"{label}.{f} = {r[f]!r} (record: {r.get('email') or r.get('userEmail')})")
    return failures


def main():
    now = int(time.time() * 1000)
    day_ago = now - 86_400_000

    spend = call("/teams/spend", {"page": 1, "pageSize": 100, "searchTerm": ""})
    events = call(
        "/teams/filtered-usage-events",
        {"startDate": day_ago, "endDate": now, "page": 1, "pageSize": 100},
    )

    spend_rows = spend.get("teamMemberSpend", [])
    event_rows = events.get("usageEvents", [])
    if not spend_rows:
        print("CANARY FAILED: /teams/spend returned zero records", file=sys.stderr)
        sys.exit(1)

    failures = check(spend_rows, SPEND_REQUIRED, [], "spend")
    failures += check(event_rows, EVENT_REQUIRED, EVENT_OPTIONAL, "usage_events")

    if failures:
        print("CANARY FAILED: null or non numeric cost fields detected:", file=sys.stderr)
        for f in failures[:20]:
            print(f"  {f}", file=sys.stderr)
        print(f"  ({len(failures)} total)", file=sys.stderr)
        sys.exit(1)

    frac = sum(1 for r in spend_rows if isinstance(r["spendCents"], float) and r["spendCents"] % 1)
    print(
        f"CANARY OK: {len(spend_rows)} spend rows, {len(event_rows)} usage events, "
        f"all cost fields numeric ({frac} spend rows with fractional cents)."
    )


if __name__ == "__main__":
    main()
