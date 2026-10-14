# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

# Throwaway probe #4 - which response headers GenVM's web.get exposes
# (Wayback's memento-datetime in particular), and redirect behaviour.

import genlayer as gl
from genlayer.types import *
from genlayer.storage import DynArray
import json


class Probe4(gl.contract.Contract):
    results: DynArray[str]

    def __init__(self) -> None:
        pass

    @gl.public.write
    def headers_of(self, url: str) -> None:
        def leader_fn() -> str:
            r = gl.nondet.web.get(url)
            hs = {k: (v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v))[:80] for k, v in r.headers.items()}
            return json.dumps({"url": url, "status": r.status, "len": len(r.body or b""), "headers": hs})

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    @gl.public.view
    def get_results(self) -> list:
        return [r for r in self.results]
