"""verify_dois.py
=================

DOI-resolution checker for ``docs/references.bib``.  Iterates the bib
file, hits ``https://doi.org/<doi>`` for every entry that carries a
``doi`` field, follows redirects, and writes a CSV report to
``docs/references_doi_check.csv``.

Exit codes
----------
    0   All ``doi``-bearing entries resolve to a 2xx or 3xx response.
        (Entries without a ``doi`` field are skipped, never count
        as failures, and appear in the CSV with ``status='no-doi'``.)
    1   At least one ``doi`` returned 4xx / 5xx, was malformed, or
        otherwise failed to resolve to a recognisable target.
    2   The script could not perform any HTTP request (e.g. network
        unreachable on the runner).  Treated as ``infrastructure
        problem`` rather than ``DOI rotted`` so CI surfaces it
        differently from a real DOI failure.

Usage
-----
    python tools/verify_dois.py [BIB_PATH] [-o CSV_PATH] [--timeout S]

If ``BIB_PATH`` is omitted, defaults to ``docs/references.bib``
relative to the current working directory.  CSV defaults to
``docs/references_doi_check.csv`` next to the bib.

This script is invoked weekly by the ``doi-watch`` job in
``.github/workflows/ci.yml`` so a rotted DOI shows up as a CI alert
rather than as a manuscript-time surprise.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Bib parsing - intentionally tiny regex parser, not a full bibtex grammar.
# Every entry in references.bib uses the canonical `field = {value}` form,
# so a regex is sufficient and avoids a third-party dependency.
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(
    r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)\n\}",
    re.DOTALL,
)
_FIELD_RE = re.compile(
    r"(?P<name>\w+)\s*=\s*\{(?P<value>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
    re.DOTALL,
)


def parse_bib(path: Path) -> list[dict]:
    """Parse ``path`` and return a list of dict entries.

    Each dict has at minimum ``key`` and ``type`` keys; optional
    ``doi``, ``year``, ``url`` etc. are populated when present.
    """
    text = path.read_text(encoding="utf-8")
    entries: list[dict] = []
    for m in _ENTRY_RE.finditer(text):
        entry = {"key": m.group("key"), "type": m.group("type").lower()}
        for fm in _FIELD_RE.finditer(m.group("body")):
            value = re.sub(r"\s+", " ", fm.group("value")).strip()
            entry[fm.group("name").lower()] = value
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# DOI resolution - HEAD first (cheap), fall back to GET if HEAD blocked.
# doi.org typically issues a 302 to the publisher's landing page; we count
# anything in {200, 301, 302, 303, 307, 308} as "resolved".
# ---------------------------------------------------------------------------

_RESOLVE_OK = {200, 301, 302, 303, 307, 308}
_HEADERS = {"User-Agent": "sambp-fault-location-id/0.1.0 (verify_dois)"}


def resolve_doi(doi: str, timeout: float) -> tuple[int | None, str]:
    """Return (status_code, final_url).

    On any network exception, status_code is ``None`` and final_url
    is the exception class name.
    """
    url = f"https://doi.org/{doi.strip()}"
    try:
        r = requests.head(
            url, allow_redirects=True, timeout=timeout, headers=_HEADERS
        )
        if r.status_code == 405:  # method not allowed -> retry with GET
            r = requests.get(
                url, allow_redirects=True, timeout=timeout, headers=_HEADERS
            )
        return r.status_code, r.url
    except requests.RequestException as exc:
        return None, type(exc).__name__


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "bib", nargs="?", default="docs/references.bib", type=Path
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="CSV report path (default: <bib_dir>/references_doi_check.csv).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HEAD request timeout in seconds (default: 5).",
    )
    args = parser.parse_args(argv)

    if not args.bib.exists():
        print(f"verify_dois: bib file not found: {args.bib}", file=sys.stderr)
        return 1

    out_path = args.out or args.bib.parent / "references_doi_check.csv"
    entries = parse_bib(args.bib)

    if not entries:
        print(f"verify_dois: no entries parsed from {args.bib}", file=sys.stderr)
        return 1

    n_total = len(entries)
    n_doi = sum(1 for e in entries if e.get("doi"))
    n_no_doi = n_total - n_doi
    n_fail = 0
    n_network_err = 0

    rows: list[dict] = []
    for entry in entries:
        row = {
            "key": entry["key"],
            "type": entry["type"],
            "year": entry.get("year", ""),
            "doi": entry.get("doi", ""),
            "status": "",
            "final_url": "",
        }
        if not entry.get("doi"):
            row["status"] = "no-doi"
        else:
            code, final = resolve_doi(entry["doi"], args.timeout)
            if code is None:
                row["status"] = f"network:{final}"
                n_network_err += 1
            elif code in _RESOLVE_OK:
                row["status"] = f"resolved:{code}"
            else:
                row["status"] = f"failed:{code}"
                n_fail += 1
            row["final_url"] = final
        rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["key", "type", "year", "doi", "status", "final_url"]
        )
        writer.writeheader()
        writer.writerows(rows)

    # ------------------ stdout summary ------------------
    print(
        f"verify_dois: parsed {n_total} entries from {args.bib}\n"
        f"  with DOI:        {n_doi}\n"
        f"  without DOI:     {n_no_doi}\n"
        f"  resolved OK:     {n_doi - n_fail - n_network_err}\n"
        f"  failed (4xx/5xx): {n_fail}\n"
        f"  network errors:  {n_network_err}\n"
        f"report written:    {out_path}"
    )

    if n_fail:
        return 1
    if n_network_err and n_fail == 0 and n_doi == n_network_err:
        # Couldn't reach the network at all -> infra problem, not DOI rot.
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
