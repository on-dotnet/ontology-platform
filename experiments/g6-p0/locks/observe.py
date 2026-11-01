"""观察既有单版本快照；使用现有pip的PEP解析器，不搜索版本、不执行求解。"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.packaging.tags import cpython_tags, compatible_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "851fa7eb2153c660b7989c0a7a6dd0e1c8e1b63c"
EXTRAS = ["convert-core", "format-pdf", "format-office", "format-markdown"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("DUPLICATE_JSON_KEY")
            out[k] = v
        return out
    def invalid_constant(value):
        raise ValueError("NON_FINITE_JSON_CONSTANT")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def safe_filename(name):
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", name)
            or ".." in name):
        raise ValueError("UNSAFE_FILENAME")


def official_url(value, host, filename=None):
    if not isinstance(value, str) or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("UNSAFE_URL")
    u = urlsplit(value)
    if (u.scheme != "https" or u.netloc != host or u.username is not None
            or any(x in value for x in ["?", "#", "\\", "\r", "\n", "\t"])
            or any(x in unquote(u.path).split("/") for x in [".", ".."])):
        raise ValueError("UNSAFE_URL")
    if filename and unquote(u.path.rsplit("/", 1)[-1]) != filename:
        raise ValueError("URL_FILENAME_MISMATCH")


def validate_nodes(nodes):
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError("INVALID_NODES")
    seen = set()
    for key, n in nodes.items():
        if not isinstance(n, dict) or not isinstance(n.get("name"), str):
            raise ValueError("INVALID_NODE")
        name = canonicalize_name(n["name"])
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name in seen or canonicalize_name(key) != name:
            raise ValueError("DUPLICATE_OR_INVALID_NAME")
        seen.add(name)
        Version(n["version"])
        official_url(n["source"], "pypi.org")
        if unquote(urlsplit(n["source"]).path) not in [f"/pypi/{name}/json", f"/pypi/{name}/{n['version']}/json"]:
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        for field in ["requiresDist", "providesExtra", "artifacts"]:
            if not isinstance(n.get(field), list):
                raise ValueError("INVALID_NODE_LIST")
        for raw in n["requiresDist"]:
            q = Requirement(raw)
            if q.url:
                raise ValueError("DIRECT_URL_REQUIREMENT_REFUSED")
        SpecifierSet(n.get("requiresPython") or "")
        artifacts = set()
        for a in n["artifacts"]:
            if not isinstance(a, dict):
                raise ValueError("INVALID_ARTIFACT")
            safe_filename(a["filename"])
            if a["filename"].casefold() in artifacts:
                raise ValueError("DUPLICATE_ARTIFACT")
            artifacts.add(a["filename"].casefold())
            if (type(a.get("size")) is not int or a["size"] <= 0
                    or not re.fullmatch(r"[0-9a-f]{64}", a.get("sha256", ""))
                    or type(a.get("yanked")) is not bool):
                raise ValueError("INVALID_ARTIFACT_FIELDS")
            official_url(a["url"], "files.pythonhosted.org", a["filename"])
            SpecifierSet(a.get("requiresPython") or "")
            if a["filename"].endswith(".whl"):
                wn, wv, _, _ = parse_wheel_filename(a["filename"])
                if canonicalize_name(wn) != name or wv != Version(n["version"]) or a["packagetype"] != "bdist_wheel":
                    raise ValueError("WHEEL_IDENTITY_MISMATCH")
    return nodes


def python_condition(spec):
    """只有整minor界限可确定；patch界限保留条件，绝不假设3.12.0。"""
    clauses = list(SpecifierSet(spec or ""))
    # 对3.12整minor明显排除的范围可拒绝；任何patch级界限均保守未知。
    if any(len(c.version.rstrip(".*").split(".")) > 2 or c.operator == "~="
           or (c.version == "3.12" and c.operator in ["==", "!=", "<=", ">"])
           for c in clauses):
        return "UNKNOWN_PATCH"
    return "MATCH_MINOR" if SpecifierSet(spec or "").contains("3.12.0") else "REJECT_MINOR"


def marker_value(q, extras, machine):
    if not q.marker:
        return True
    text = str(q.marker)
    unknown = ["python_full_version", "implementation_version", "platform_release", "platform_version"]
    if any(re.search(r"\b" + k + r"\b", text) for k in unknown):
        return None
    env = dict(implementation_name="cpython", platform_python_implementation="CPython",
               os_name="posix", sys_platform="linux", platform_system="Linux",
               platform_machine=machine, python_version="3.12",
               python_full_version="UNKNOWN", implementation_version="UNKNOWN",
               platform_release="UNKNOWN", platform_version="UNKNOWN")
    return any(q.marker.evaluate(dict(env, extra=e)) for e in [""] + sorted(extras))


def wheel_candidates(n, machine):
    if python_condition(n.get("requiresPython")) == "REJECT_MINOR":
        return []
    rows = []
    for a in n["artifacts"]:
        if a["packagetype"] != "bdist_wheel" or a["yanked"]:
            continue
        _, _, _, tags = parse_wheel_filename(a["filename"])
        matching = []
        for t in sorted(tags, key=str):
            floor = None
            if t.platform != "any":
                m = re.fullmatch(r"manylinux_(\d+)_(\d+)_" + re.escape(machine), t.platform)
                legacy = {"manylinux1_x86_64": [2, 5], "manylinux2010_x86_64": [2, 12],
                          "manylinux2014_x86_64": [2, 17], "manylinux2014_aarch64": [2, 17]}
                if m:
                    floor = [int(m[1]), int(m[2])]
                elif t.platform in legacy and t.platform.endswith("_" + machine):
                    floor = legacy[t.platform]
                else:
                    continue
            supported = set(cpython_tags((3, 12), abis=["cp312"], platforms=[t.platform]))
            supported.update(compatible_tags((3, 12), interpreter="cp312", platforms=[t.platform]))
            if t in supported:
                matching.append(dict(tag=str(t), minimumGlibc=floor))
        if matching and python_condition(a.get("requiresPython")) != "REJECT_MINOR":
            rows.append(dict(filename=a["filename"], sha256=a["sha256"], size=a["size"],
                             url=a["url"], tags=matching, requiresPython=a.get("requiresPython"),
                             pythonCondition=python_condition(a.get("requiresPython")),
                             status="CONDITIONAL_REGISTRY_CANDIDATE_NOT_SELECTED",
                             hashKind="REGISTRY_DECLARED_NOT_PAYLOAD_VERIFIED"))
    return sorted(rows, key=lambda r: r["filename"])


def observe(nodes, machine):
    """传播单快照已观察节点，不回溯、不选择、不报告UNSAT。"""
    active = {"docling-slim": set(EXTRAS)}
    changed = True
    while changed:
        changed = False
        for name, extras in list(active.items()):
            if name not in nodes:
                continue
            for raw in nodes[name]["requiresDist"]:
                q = Requirement(raw)
                if marker_value(q, extras, machine) is True:
                    dep = canonicalize_name(q.name)
                    if dep not in active:
                        active[dep] = set(); changed = True
                    before = len(active[dep]); active[dep].update(q.extras)
                    changed |= len(active[dep]) != before
    edges, conflicts, unknown = [], [], []
    for name, extras in sorted(active.items()):
        if name not in nodes:
            unknown.append(dict(code="MISSING_SNAPSHOT_NODE", name=name)); continue
        for raw in nodes[name]["requiresDist"]:
            q = Requirement(raw); m = marker_value(q, extras, machine)
            if m is None:
                unknown.append(dict(code="UNKNOWN_TARGET_MARKER", parent=name, requirement=raw))
            elif m:
                dep = canonicalize_name(q.name); n = nodes.get(dep)
                ok = n is not None and q.specifier.contains(n["version"])
                edge = dict(parent=name, requirement=raw, dependency=dep,
                            observedVersion=n["version"] if n else None, observedSatisfies=ok)
                edges.append(edge)
                if not ok:
                    conflicts.append(edge)
        absent = extras - set(nodes[name]["providesExtra"])
        if absent:
            unknown.append(dict(code="UNKNOWN_EXTRA", name=name, extras=sorted(absent)))
    rows = []
    for name, extras in sorted(active.items()):
        if name not in nodes:
            continue
        n = nodes[name]; wheels = wheel_candidates(n, machine)
        rows.append(dict(name=name, observedVersion=n["version"], selectedExtras=sorted(extras),
                         requiresPython=n["requiresPython"], pythonCondition=python_condition(n["requiresPython"]),
                         metadataSource=n["source"], metadataRawSha256=n["rawMetadataSha256"],
                         metadataRetrievedAtUtc=n["retrievedAtUtc"],
                         licenseExpression=n.get("licenseExpression"), licenseDeclared=n.get("licenseDeclared"),
                         licenseStatus="DECLARED_ONLY_NOTICE_NOT_VERIFIED", securityAudit=None,
                         securityExplanation="PyPI advisory metadata is not an independent security audit",
                         artifactNotice="NOT_VERIFIED", selectedWheel=None, candidates=wheels,
                         status="METADATA_OBSERVED" if wheels else "BLOCKED_NO_WHEEL_IN_OBSERVED_VERSION"))
    return dict(machine=machine, status="BLOCKED_WITH_WITNESS", resolverRun="NOT_RUN", solution=None,
                selectedWheels=None, packages=rows, declarations=edges, snapshotConflicts=conflicts,
                unknown=unknown, noWheelObserved=[r["name"] for r in rows if not r["candidates"]],
                warning="No version search; snapshot conflicts/missing wheels are not proof of global UNSAT")


def require_real_solution(result):
    if (result.get("resolverRun") != "SUCCESS" or result.get("solution") is None
            or result.get("selectedWheels") is None):
        raise ValueError("NOT_A_LOCK_NO_SUCCESSFUL_RESOLVER")


def validate_profile(profile, nodes):
    expected = dict(name="docling-slim", version="2.145.0", extras=EXTRAS,
                    root="docling-slim[convert-core,format-pdf,format-office,format-markdown]==2.145.0",
                    pythonMinor="3.12", pythonPatch=None, glibc=None, baseImageDigest=None,
                    targets=[dict(id="T1", oci="linux/arm64", machine="aarch64"),
                             dict(id="T2", oci="linux/amd64", machine="x86_64")])
    if any(profile.get(k) != v for k, v in expected.items()):
        raise ValueError("PROFILE_CONTRACT_MISMATCH")
    if nodes.get("docling-slim", {}).get("version") != expected["version"]:
        raise ValueError("ROOT_VERSION_MISMATCH")


def build():
    source = ROOT / "experiments/g6-p0/supply-chain/pypi-metadata.json"
    raw = source.read_bytes(); nodes = validate_nodes(strict_json(raw)["nodes"])
    validate_profile(strict_json((HERE / "docling-lite-profile.json").read_bytes()), nodes)
    inputs = {}
    for p in sorted((ROOT / "experiments/g6-p0/supply-chain").glob("*.json")):
        inputs[str(p.relative_to(ROOT))] = digest(p.read_bytes())
    for name in ["docling-lite-profile.json", "observe.py"]:
        inputs[str((HERE / name).relative_to(ROOT))] = digest((HERE / name).read_bytes())
    return dict(schemaVersion=1, kind="OBSERVED_SINGLE_VERSION_GRAPH_NOT_LOCK", baseSha=BASE,
                inputSha256=inputs, profileSha256=inputs["experiments/g6-p0/locks/docling-lite-profile.json"],
                metadataSnapshotSha256=digest(raw), status="BLOCKED_WITH_WITNESS",
                blocker=dict(code="RESOLVER_TOOL_APPROVAL_REQUIRED", installedTool="pip 26.2.2",
                             witness="pip prepare.py lines 507-511, 664, 735: metadata fallback can unpack/download wheel; dry-run does not forbid it",
                             solverExecuted=False, payloadDownloaded=False),
                scope="Conditional CPython3.12 manylinux candidates; Python patch/glibc/image not frozen",
                platforms={k: observe(nodes, m) for k, m in [("T1", "aarch64"), ("T2", "x86_64")]})


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
