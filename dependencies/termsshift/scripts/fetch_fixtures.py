"""
Downloads the Internet Archive captures the tests run against into
tests/fixtures/cache/ and verifies each one's SHA-256.

Why download instead of committing them: they are Circle's and Tether's
own terms of service. This repo doesn't redistribute anyone's legal text -
it pins the exact archived captures by timestamp and hash, which are
immutable, so every run gets byte-identical inputs.

The archive stores some captures gzip-encoded and serves them that way;
GenVM's fetcher decompresses transparently (confirmed live - see
research/README.md), so this script does the same and hashes the result.

Usage (from the repo root):  python3 scripts/fetch_fixtures.py
          --record            refresh the sha256 values in the manifest
"""

import gzip
import hashlib
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "fixtures" / "manifest.json"
CACHE = ROOT / "tests" / "fixtures" / "cache"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "TermsShift fixture fetch"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
            return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
        except Exception as exc:  # the archive is occasionally slow - retry
            if attempt == 3:
                raise
            print(f"  retrying {url} ({exc})")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def main() -> None:
    record = "--record" in sys.argv
    manifest = json.loads(MANIFEST.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, entry in manifest["captures"].items():
        target = CACHE / f"{name}.html"
        body = target.read_bytes() if target.exists() else fetch(entry["url"])
        digest = hashlib.sha256(body).hexdigest()
        if record:
            entry["sha256"] = digest
        elif digest != entry["sha256"]:
            raise SystemExit(f"{name}: sha256 {digest} != manifest {entry['sha256']}")
        target.write_bytes(body)
        print(f"{name}: {len(body)} bytes, sha256 {digest[:16]}... ok")
    if record:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
