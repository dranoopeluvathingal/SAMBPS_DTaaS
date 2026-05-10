"""tools/fetch_cnrs_dataset.py
=================================
Fetch the CNRS / Recherche Data Gouv IEEE 34-node HIF dataset
(Pereira de Souza et al. 2024, DOI 10.57745/KRYCYY) into
``data/cnrs_ieee34/`` for the WP3.7 external-validation pipeline.

Default behaviour
-----------------

By default this script downloads the LIGHT artefacts only:

* ``data_explanation.pdf`` -- dataset schema + provenance.
* ``data_read.py``         -- author-provided Python read helper.
* ``IEEE_34_node_HIF.pdf`` -- the IEEE 34 case description.
* ``train.zip``            -- training-split waveforms (~75 MB).

The ~3 GB ``test.zip`` is held back behind the ``--include-test``
flag because it bloats the dev box.  WP3.7 acceptance only needs
``train.zip`` (the test split is reserved for the lead engineer's
licensed Windows runner per the WP3.7 brief follow-up).

Per-file SHA-256 sums are appended to
``data/cnrs_ieee34/MANIFEST.sha256`` after each download (the
manifest is overwritten when ``--rehash`` is passed; otherwise
new lines are appended).

Endpoint
--------

The dataset lives at the Recherche Data Gouv "Dataverse" instance:
https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/KRYCYY

Files are fetched via the Dataverse "access/datafile/{id}" API which
streams the raw content with no DSL parsing required.  License is
**etalab 2.0** (open licence, equivalent to CC-BY for redistribution
purposes), recorded in the manifest.

Usage
-----

    python tools/fetch_cnrs_dataset.py
    python tools/fetch_cnrs_dataset.py --include-test
    python tools/fetch_cnrs_dataset.py --rehash    # recompute SHA-256s

Citation
--------

Pereira de Souza, F. et al. (2024) "IEEE 34 node HIF dataset",
Recherche Data Gouv, https://doi.org/10.57745/KRYCYY.
Bib key: ``PereiraDeSouza2024CNRS`` (see references.bib).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = PROJ_ROOT / "data" / "cnrs_ieee34"

DOI = "doi:10.57745/KRYCYY"
DATAVERSE_BASE = "https://entrepot.recherche.data.gouv.fr"
METADATA_URL = (
    f"{DATAVERSE_BASE}/api/datasets/:persistentId/?persistentId={DOI}"
)
ACCESS_URL = f"{DATAVERSE_BASE}/api/access/datafile"

LIGHT_FILES = {
    "data_explanation.pdf",
    "data_read.py",
    "IEEE_34_node_HIF.pdf",
    "train.zip",
}
HEAVY_FILES = {"test.zip"}


def _fetch_url(url: str, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _stream_to_file(url: str, dest: Path, *, timeout: float = 600.0) -> int:
    """Stream a URL to a file, returning the number of bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with urllib.request.urlopen(url, timeout=timeout) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            n += len(chunk)
    return n


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _list_files() -> list[dict]:
    raw = _fetch_url(METADATA_URL)
    data = json.loads(raw.decode("utf-8"))
    if data.get("status") != "OK":
        raise RuntimeError(
            f"Recherche Data Gouv API returned status "
            f"{data.get('status')!r}; full response: {data!r}"
        )
    return data["data"]["latestVersion"]["files"]


def _select_files(
    file_list: list[dict],
    *,
    include_test: bool,
) -> list[dict]:
    desired = set(LIGHT_FILES)
    if include_test:
        desired |= HEAVY_FILES
    out: list[dict] = []
    for f in file_list:
        df = f["dataFile"]
        if df["filename"] in desired:
            out.append(df)
    return sorted(out, key=lambda d: d["filename"])


def _write_manifest_line(path: Path, sha: str, size: int, append: bool) -> None:
    target_dir = TARGET_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = target_dir / "MANIFEST.sha256"
    mode = "a" if append else "w"
    with manifest.open(mode) as fh:
        fh.write(f"{sha}  {size:>12}  {path.name}\n")


def fetch(include_test: bool = False, rehash: bool = False) -> None:
    print(
        f"WP3.7 CNRS dataset fetch: target {TARGET_DIR}; "
        f"include_test = {include_test}; rehash = {rehash}"
    )
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    manifest = TARGET_DIR / "MANIFEST.sha256"
    if rehash and manifest.exists():
        manifest.unlink()
    files = _list_files()
    selected = _select_files(files, include_test=include_test)
    if not selected:
        print(
            "no light or selected files matched the dataset listing.\n"
            "Available filenames:\n"
            + "\n".join(f"  {f['dataFile']['filename']}" for f in files)
        )
        return
    print(f"selected {len(selected)} files:")
    for df in selected:
        print(
            f"  {df['filename']:<32}  "
            f"{df['filesize']:>12} bytes  "
            f"{df.get('contentType', 'application/octet-stream')}"
        )

    # Header line on first write.
    if not manifest.exists():
        with manifest.open("w") as fh:
            fh.write(
                "# WP3.7 CNRS IEEE 34-node HIF dataset\n"
                f"# DOI: {DOI}\n"
                "# License: etalab 2.0\n"
                "# Format: <sha256>  <bytes>  <filename>\n"
            )

    for df in selected:
        dest = TARGET_DIR / df["filename"]
        if dest.exists() and not rehash:
            actual = _sha256_of_file(dest)
            print(
                f"  {df['filename']}: already on disk "
                f"({dest.stat().st_size} bytes; sha256 {actual[:16]}...)"
            )
            _write_manifest_line(
                dest, actual, dest.stat().st_size, append=True,
            )
            continue
        url = f"{ACCESS_URL}/{df['id']}"
        print(f"  fetching {df['filename']} from {url} ...", flush=True)
        n = _stream_to_file(url, dest)
        sha = _sha256_of_file(dest)
        print(
            f"    -> wrote {n} bytes; sha256 = {sha}"
        )
        _write_manifest_line(dest, sha, n, append=True)

    print(f"\nmanifest written to {manifest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--include-test", action="store_true",
        help="Also fetch the ~3 GB test.zip; default is train.zip-only.",
    )
    parser.add_argument(
        "--rehash", action="store_true",
        help="Recompute SHA-256 sums for files already on disk and "
        "rewrite the manifest from scratch.",
    )
    args = parser.parse_args(argv)
    fetch(include_test=args.include_test, rehash=args.rehash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
