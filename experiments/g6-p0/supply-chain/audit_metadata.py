"""只读已冻结元数据生成声明图审计；不联网、不安装，不冒充PEP508版本求解器。"""
import json
from pathlib import Path
import re


def audit(data):
    nodes = data["nodes"]
    extras = {k:set(v) for k,v in data["selectedExtras"].items()}
    missing = set(); missing_extras = set(); edges = []; pins = []
    for name,node in nodes.items():
        for req in node.get("requiresDist", []):
            gates = re.findall(r"extra\s*==\s*[\"']([^\"']+)", req)
            if gates and not set(gates) & extras.get(name,set()): continue
            m = re.match(r"([A-Za-z0-9_.-]+)(?:\[([^]]+)\])?", req)
            if not m: raise ValueError("UNPARSED_REQUIREMENT")
            dep = re.sub(r"[-_.]+", "-", m[1]).lower()
            edges.append({"from":name,"to":dep,"requirement":req})
            if dep not in nodes: missing.add(dep)
            for extra in (m[2].split(",") if m[2] else []):
                if extra not in extras.get(dep,set()): missing_extras.add(dep+"["+extra+"]")
            pin = re.search(r"(?<![!<>=])==([0-9][A-Za-z0-9_.+-]*)(?=[,; ]|$)", req)
            if pin and nodes.get(dep,{}).get("version") != pin[1]:
                pins.append({"from":name,"name":dep,"required":pin[1],"observed":nodes.get(dep,{}).get("version")})
    return {"nodeCount":len(nodes),"selectedDeclarationEdges":len(edges),"missingNodes":sorted(missing),
        "unpropagatedExtras":sorted(missing_extras),"exactPinMismatches":pins,
        "graphEnumeration":"PASS" if not missing and not missing_extras else "INCOMPLETE",
        "installClosure":"BLOCKED_PLATFORM_MARKERS_CONSTRAINTS_LICENSES_NATIVE_LIBS",
        "securityAudit":"NOT_RUN", "artifactDownloads":0}


if __name__ == "__main__":
    path=Path(__file__).resolve().parent
    print(json.dumps(audit(json.loads((path/"pypi-metadata.json").read_text())),ensure_ascii=False,indent=2))
