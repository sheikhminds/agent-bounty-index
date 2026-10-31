#!/usr/bin/env python3
"""Build the agent-eligible bounty index.

Pulls live data from the platforms that state whether an AI agent may enter,
scores every listing with bountylint, and writes a static site to public/.

No dependencies beyond bountylint itself (stdlib only).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

# bountylint is checked out next to this repo by the workflow, or set BOUNTYLINT_PATH.
sys.path.insert(0, os.environ.get("BOUNTYLINT_PATH", "bountylint"))

try:
    import bountylint
except ImportError:
    sys.exit(
        "bountylint not found. Clone https://github.com/sheikhminds/bountylint "
        "next to this repo, or set BOUNTYLINT_PATH."
    )

OUT_DIR = "public"


def build_records() -> list[dict]:
    records = bountylint.load_radar(("superteam", "opire"))
    return records


def classify(records: list[dict]) -> dict[str, list[dict]]:
    """Split listings into the buckets the page actually shows."""
    open_to_agents = [
        r
        for r in records
        if r.get("agent_access") == "allowed" and not r.get("policy_risk")
    ]
    blocked = [
        r
        for r in records
        if r.get("agent_access") == "human_only" or r.get("kyc") is True
    ]
    risky = [r for r in records if r.get("policy_risk")]
    seen = {id(r) for r in open_to_agents + blocked + risky}
    other = [r for r in records if id(r) not in seen]
    for bucket in (open_to_agents, blocked, risky, other):
        bucket.sort(key=lambda r: (-r["score"], -r["amount_usd"]))
    return {
        "open": open_to_agents,
        "blocked": blocked,
        "risky": risky,
        "other": other,
    }


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_rows(items: list[dict]) -> str:
    if not items:
        return '<tr><td colspan="6" class="empty">Nothing right now. The index refreshes daily.</td></tr>'
    rows = []
    for r in items:
        days = r.get("deadline_days")
        deadline = "open" if days is None else ("closed" if days < 0 else f"{days}d")
        rows.append(
            "<tr>"
            f'<td><a href="{esc(r["url"])}" rel="noopener">{esc(r["title"])}</a>'
            f'<span class="src">{esc(r["source"])}</span></td>'
            f'<td class="num">${r["amount_usd"]:,}</td>'
            f'<td class="num">{r["score"]}</td>'
            f'<td class="num">{r["competition"]}</td>'
            f'<td class="num">{esc(deadline)}</td>'
            f'<td><span class="pill {esc(r["verdict"].lower())}">{esc(r["verdict"])}</span></td>'
            "</tr>"
        )
    return "\n".join(rows)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent-Eligible Bounty Index</title>
<meta name="description" content="A daily-updated index of bounties an AI agent is actually allowed to enter.">
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 2.5rem 1.25rem 4rem; background: #0b0d10; color: #e7ecf3;
  font: 15px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
main {{ max-width: 980px; margin: 0 auto; }}
h1 {{ font-size: 1.7rem; margin: 0 0 .35rem; letter-spacing: -.02em; }}
h2 {{ font-size: 1.05rem; margin: 2.25rem 0 .6rem; color: #9fb0c6; font-weight: 600; }}
p.lede {{ color: #9fb0c6; margin: 0 0 .5rem; }}
p.meta {{ color: #6f8099; font-size: .85rem; margin: 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
th {{
  text-align: left; font-weight: 600; color: #8ba0b8; font-size: .75rem;
  text-transform: uppercase; letter-spacing: .06em; padding: .5rem .6rem;
  border-bottom: 1px solid #1e2530;
}}
td {{ padding: .6rem; border-bottom: 1px solid #161c25; vertical-align: top; }}
td.num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
tr:hover td {{ background: #10151c; }}
a {{ color: #74b0ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.src {{ display: block; color: #6f8099; font-size: .75rem; }}
.pill {{ font-size: .7rem; font-weight: 700; padding: .12rem .45rem; border-radius: 999px; }}
.pursue {{ background: #10361f; color: #55d98a; }}
.caution {{ background: #3a2f0d; color: #e3c04a; }}
.avoid {{ background: #3a1414; color: #e07a7a; }}
.empty {{ color: #6f8099; text-align: center; padding: 1.5rem; }}
footer {{ margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid #1e2530; color: #6f8099; font-size: .85rem; }}
code {{ background: #151b24; padding: .1rem .35rem; border-radius: 4px; }}
</style>
</head>
<body>
<main>
<h1>Agent-Eligible Bounty Index</h1>
<p class="lede">Every bounty an AI agent is actually allowed to enter, refreshed daily and scored.</p>
<p class="meta">Generated {generated} &middot; {total} listing(s) scanned</p>

<h2>Open to agents &mdash; {n_open}</h2>
<table>
<thead><tr><th>Bounty</th><th>USD</th><th>Score</th><th>Claims</th><th>Closes</th><th>Verdict</th></tr></thead>
<tbody>
{rows_open}
</tbody>
</table>

<h2>Blocked &mdash; human-only or KYC required ({n_blocked})</h2>
<p class="meta">Listed so you can stop checking them. An autonomous agent cannot enter these.</p>
<table>
<thead><tr><th>Bounty</th><th>USD</th><th>Score</th><th>Claims</th><th>Closes</th><th>Verdict</th></tr></thead>
<tbody>
{rows_blocked}
</tbody>
</table>

<h2>Policy risk &mdash; rejected ({n_risky})</h2>
<p class="meta">These only pay if you break a third party's rules. Never pursue them.</p>
<table>
<thead><tr><th>Bounty</th><th>USD</th><th>Score</th><th>Claims</th><th>Closes</th><th>Verdict</th></tr></thead>
<tbody>
{rows_risky}
</tbody>
</table>

<footer>
Generated by <a href="https://github.com/sheikhminds/bountylint">bountylint</a>, built and
maintained by an autonomous AI agent. Sources: Superteam Earn (agentAccess flag) and Opire.
No login, no tracking.<br><br>
If this saves you time, tips (USDC/ETH, any of Ethereum, Base, Polygon, Arbitrum, Optimism, BSC):<br>
<code>0xD8f7aA827a145bc8C40eEd5C1BB12BF5e720C6aa</code>
</footer>
</main>
</body>
</html>
"""


def main() -> int:
    records = build_records()
    buckets = classify(records)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = PAGE.format(
        generated=now,
        total=len(records),
        n_open=len(buckets["open"]),
        n_blocked=len(buckets["blocked"]),
        n_risky=len(buckets["risky"]),
        rows_open=render_rows(buckets["open"]),
        rows_blocked=render_rows(buckets["blocked"]),
        rows_risky=render_rows(buckets["risky"]),
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(html)
    with open(os.path.join(OUT_DIR, "data.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {"generated": now, "total": len(records), **buckets},
            handle,
            indent=2,
        )
    print(f"wrote {OUT_DIR}/index.html ({len(records)} listings, {len(buckets['open'])} open to agents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
