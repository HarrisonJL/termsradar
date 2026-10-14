"""
The trust path in TRUST_PATH.md, checked offline.

TermsRadar is a deterministic policy: it has no web access and no LLM. Everything non-deterministic (reading the
issuer's live terms, the reader, validator consensus) happens in TermsShift, whose exact deployed source is included
under dependencies/termsshift. These tests pin the properties a reviewer relies on when following the path from the
issuer's page to an allocation, so the path cannot silently break:

  - the included dependency is the deployed code (by SHA-256; studio-next/verify_dependency.ts checks the chain itself);
  - the dependency really does the non-deterministic work and the radar does none of it;
  - every view the radar calls exists in the dependency, and every verdict the dependency can record is handled;
  - a sign-off is bound to the same per-area digests the dependency records;
  - everything points at one deployed dependency; the trust-path document is current.
"""
import ast
import hashlib
import importlib.util
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
DEP_DIR = REPO / "dependencies" / "termsshift"
DEP = DEP_DIR / "contracts" / "terms_shift_studio_next.py"
RADAR = REPO / "contracts" / "terms_radar_studio_next.py"

DEPLOYED_SHA256 = "72dcd10612b9b43c3e8bb667274467591cebb17b3f22d20f294c6ab36da7f1c3"
SHIFT_ADDRESS = "0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69"


def _function(path: pathlib.Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name}")


def _strings(node: ast.AST) -> set:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _strings_with_constants(path: pathlib.Path, name: str) -> set:
    """The strings a function uses, including those it reaches through module-level constants (ADVERSE = "...")."""
    tree = ast.parse(path.read_text())
    constants = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                 and isinstance(n.value.value, str) for t in n.targets if isinstance(t, ast.Name)}
    func = _function(path, name)
    return _strings(func) | {constants[n.id] for n in ast.walk(func) if isinstance(n, ast.Name) and n.id in constants}


def test_the_included_dependency_is_the_deployed_code():
    assert hashlib.sha256(DEP.read_bytes()).hexdigest() == DEPLOYED_SHA256


def test_the_included_dependency_is_complete():
    for rel in ("LICENSE", "README.md", "CONTRACT.md", "contracts/terms_shift.py", "contracts/terms_shift_studio_next.py",
                "tests/test_terms_shift.py", "tests/fixtures/manifest.json", "scripts/fetch_fixtures.py"):
        assert (DEP_DIR / rel).is_file(), f"dependencies/termsshift/{rel} is missing"


def test_the_dependency_does_the_non_deterministic_work_and_the_radar_does_none_of_it():
    dep, radar = DEP.read_text(), RADAR.read_text()
    for needed in ("gl.nondet.web.get", "gl.nondet.exec_prompt", "gl.vm.run_nondet"):
        assert needed in dep, f"TermsShift no longer uses {needed}"
        assert needed not in radar, f"TermsRadar must stay deterministic but uses {needed}"


def test_every_view_the_radar_calls_exists_in_the_dependency():
    called = set(re.findall(r"\.view\(\)\.(\w+)\(", RADAR.read_text()))
    assert called == {"latest_check", "list_watches"}, called
    views = set(re.findall(r"@gl\.public\.view\s+def (\w+)\(", DEP.read_text()))
    assert called <= views, f"TermsShift has no view {called - views}"


def test_every_verdict_the_dependency_can_record_is_handled_by_the_radar():
    recorded = set()
    for node in ast.walk(_function(DEP, "_decide")):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.List) and node.value.elts:
            first = node.value.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                recorded.add(first.value)
    assert recorded == {"UNDETERMINED", "MATERIAL_ADVERSE_CHANGE", "CHANGED_NOT_ADVERSE", "UNCHANGED"}, recorded
    handled = _strings_with_constants(RADAR, "_posture")
    assert recorded | {"NONE"} <= handled, f"the radar does not handle {(recorded | {'NONE'}) - handled}"
    # latest_check answers {"verdict": "NONE"} for a watch that has never been checked
    assert "NONE" in _strings(_function(DEP, "latest_check")) or '"NONE"' in DEP.read_text()


def test_a_sign_off_is_bound_to_the_digests_the_dependency_records():
    assert "excerpt_digest" in DEP.read_text(), "TermsShift no longer records a digest of the changed wording"
    assert "excerpt_digest" in _strings(_function(RADAR, "_change_digest"))


def test_the_radar_reads_the_fields_the_dependency_stores():
    stored = _strings(_function(DEP, "_check_dict"))
    for field in ("check_id", "verdict", "checked_at", "facts", "labels", "readings", "submitted_by"):
        assert field in stored, f"TermsShift's check record has no {field}"
    used = _strings(_function(RADAR, "_posture")) | _strings(_function(RADAR, "_change_digest"))
    assert {"verdict", "checked_at", "facts"} <= used


def test_everything_points_at_one_deployed_dependency():
    for rel in ("studio-next/deployment.json", "web/src/lib/radar.ts", "dependencies/termsshift/CONTRACT.md",
                "dependencies/README.md", "README.md", "TRUST_PATH.md", "studio-next/verify_dependency.ts"):
        assert SHIFT_ADDRESS in (REPO / rel).read_text(), f"{rel} does not name TermsShift at {SHIFT_ADDRESS}"
    assert json.loads((REPO / "studio-next" / "deployment.json").read_text())["shift"]["address"] == SHIFT_ADDRESS


def test_the_trust_path_document_is_current():
    spec = importlib.util.spec_from_file_location("build_trust_path", REPO / "scripts" / "build_trust_path.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (REPO / "TRUST_PATH.md").read_text() == module.TEXT, "TRUST_PATH.md is stale: run scripts/build_trust_path.py"
