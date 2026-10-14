# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

# Throwaway probe #3 - SEC EDGAR with a declared User-Agent, multi-MB
# documents, Wayback id_ snapshots (gzip?), and stdlib availability.

import genlayer as gl
from genlayer.types import *
from genlayer.storage import DynArray
import json
import hashlib


class Probe3(gl.contract.Contract):
    results: DynArray[str]

    def __init__(self) -> None:
        pass

    @gl.public.write
    def probe_get(self, url: str, user_agent: str) -> None:
        def leader_fn() -> str:
            headers = {"User-Agent": user_agent} if user_agent else {}
            try:
                r = gl.nondet.web.get(url, headers=headers)
            except Exception as e:
                return json.dumps({"url": url, "ua": bool(user_agent), "error": repr(e)[:400]})
            body = r.body or b""
            enc = r.headers.get("content-encoding", b"")
            return json.dumps({
                "url": url, "ua": bool(user_agent), "status": r.status, "len": len(body),
                "magic": body[:4].hex(), "content_encoding": str(enc)[:40],
                "sha256": hashlib.sha256(body).hexdigest(),
                "has_auditor_heading": b"Accounting Firm" in body or b"ACCOUNTING FIRM" in body,
                "head": body[:160].decode("utf-8", "replace"),
            })

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    @gl.public.write
    def probe_modules(self) -> None:
        def leader_fn() -> str:
            out = {}
            for name in ("difflib", "gzip", "zlib", "unicodedata", "html"):
                try:
                    __import__(name)
                    out[name] = "ok"
                except Exception as e:
                    out[name] = repr(e)[:120]
            try:
                import difflib
                sm = difflib.SequenceMatcher(None, ["a", "b", "c"], ["a", "x", "c"], autojunk=False)
                out["difflib_ops"] = [op[0] for op in sm.get_opcodes()]
            except Exception as e:
                out["difflib_ops"] = repr(e)[:120]
            try:
                import gzip
                out["gzip_roundtrip"] = gzip.decompress(gzip.compress(b"hello")) == b"hello"
            except Exception as e:
                out["gzip_roundtrip"] = repr(e)[:120]
            return json.dumps(out)

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    @gl.public.view
    def get_results(self) -> list:
        return [r for r in self.results]
