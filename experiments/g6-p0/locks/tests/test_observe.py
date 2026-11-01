"""当前受限合同的正反断言；测试基础设施仅使用标准库。"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lock_observer", HERE / "observe.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def node(name="docling-slim", version="2.145.0", requirements=None):
    filename = name.replace("-", "_") + "-" + version + "-py3-none-any.whl"
    return dict(name=name, version=version, source=f"https://pypi.org/pypi/{name}/{version}/json",
                requiresDist=requirements or [], providesExtra=m.EXTRAS.copy(), requiresPython=">=3.10",
                artifacts=[dict(filename=filename, size=10, sha256="a" * 64,
                                url="https://files.pythonhosted.org/packages/" + filename,
                                packagetype="bdist_wheel", yanked=False, requiresPython=">=3.10")],
                rawMetadataSha256="b" * 64, retrievedAtUtc="2026-11-01T00:00:00Z",
                licenseDeclared="MIT", licenseExpression=None)


class ContractTests(unittest.TestCase):
    def test_valid_node(self):
        self.assertEqual(m.validate_nodes({"docling-slim": node()})["docling-slim"]["version"], "2.145.0")

    def test_reject_urls(self):
        for u in ["http://pypi.org/a", "https://pypi.org.evil/a", "https://@pypi.org/a",
                  "https://pypi.org/a?", "https://pypi.org/a#", "https://pypi.org:443/a",
                  "https://pypi.org/%2e%2e/a", "https://pypi.org/a\n", " https://pypi.org/a", "\x00https://pypi.org/a"]:
            with self.subTest(u=u), self.assertRaises(ValueError):
                m.official_url(u, "pypi.org")

    def test_reject_paths(self):
        for name in ["../x.whl", "/x.whl", "a\\x.whl", "a:x.whl", "x.whl ", "x\n.whl"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.safe_filename(name)

    def test_duplicate_normalized_name(self):
        with self.assertRaises(ValueError):
            m.validate_nodes({"docling-slim": node(), "docling_slim": node()})

    def test_non_finite_json(self):
        for value in ["NaN", "Infinity", "-Infinity"]:
            with self.assertRaisesRegex(ValueError, "NON_FINITE"):
                m.strict_json('{"value":' + value + '}')

    def test_duplicate_json(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            m.strict_json('{"nodes":{},"nodes":{}}')

    def test_duplicate_artifact(self):
        n = node(); n["artifacts"].append(copy.deepcopy(n["artifacts"][0]))
        with self.assertRaises(ValueError):
            m.validate_nodes({"docling-slim": n})

    def test_malformed_artifact(self):
        for key, value in [("size", True), ("size", -1), ("sha256", "x"), ("yanked", 0)]:
            n = node(); n["artifacts"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_nodes({"docling-slim": n})

    def test_bad_requirements_and_urls(self):
        for req in ["invalid >=!", "foo @ https://evil.invalid/foo.whl"]:
            with self.assertRaises(ValueError):
                m.validate_nodes({"docling-slim": node(requirements=[req])})

    def test_wheel_identity_and_url(self):
        for field, value in [("filename", "other-2.145.0-py3-none-any.whl"),
                             ("url", "https://files.pythonhosted.org/other.whl")]:
            n = node(); n["artifacts"][0][field] = value
            with self.assertRaises(ValueError):
                m.validate_nodes({"docling-slim": n})

    def test_yanked_no_wheel(self):
        n = node(); n["artifacts"][0]["yanked"] = True
        r = m.observe({"docling-slim": n}, "aarch64")
        self.assertEqual(r["noWheelObserved"], ["docling-slim"])
        self.assertIsNone(r["solution"])

    def test_pin_conflict_not_unsat(self):
        n = node(requirements=["foo==1.0"])
        r = m.observe({"docling-slim": n, "foo": node("foo", "2.0")}, "aarch64")
        self.assertEqual(len(r["snapshotConflicts"]), 1)
        self.assertIn("not proof of global UNSAT", r["warning"])

    def test_extras_fixed_point(self):
        a = node(requirements=['foo[x]>=1; extra == "format-pdf"', 'bad; extra == "standard"'])
        b = node("foo", "1.0", ['bar>=1; extra == "x"']); b["providesExtra"] = ["x"]
        r = m.observe({"docling-slim": a, "foo": b, "bar": node("bar", "1.0")}, "x86_64")
        self.assertEqual([p["name"] for p in r["packages"]], ["bar", "docling-slim", "foo"])
        self.assertEqual(r["unknown"], [])

    def test_unknown_extra_missing_node(self):
        r = m.observe({"docling-slim": node(requirements=['foo[x]>=1'])}, "aarch64")
        self.assertEqual(r["unknown"][0]["code"], "MISSING_SNAPSHOT_NODE")
        a = node(); a["providesExtra"] = []
        self.assertEqual(m.observe({"docling-slim": a}, "aarch64")["unknown"][0]["code"], "UNKNOWN_EXTRA")

    def test_patch_not_fabricated(self):
        q = m.Requirement('foo; python_full_version >= "3.12.1"')
        self.assertIsNone(m.marker_value(q, set(), "aarch64"))
        for value in [">=3.12.1", "==3.12", ">3.12", "<=3.12", "!=3.12"]:
            self.assertEqual(m.python_condition(value), "UNKNOWN_PATCH")
        self.assertEqual(m.python_condition(">=3.13"), "REJECT_MINOR")
        self.assertEqual(m.python_condition(">=3.10,<4"), "MATCH_MINOR")

    def test_no_host_marker_leak(self):
        q = m.Requirement('foo; sys_platform == "linux" and platform_machine == "aarch64" and python_version == "3.12"')
        self.assertTrue(m.marker_value(q, set(), "aarch64"))
        self.assertFalse(m.marker_value(q, set(), "x86_64"))

    def test_node_requires_python(self):
        n = node(); n["requiresPython"] = ">=3.13"
        self.assertEqual(m.wheel_candidates(n, "aarch64"), [])

    def test_platform_abi_tags(self):
        cases = [("cp312-cp312-manylinux_2_28_aarch64", "aarch64", True),
                 ("cp311-abi3-manylinux2014_aarch64", "aarch64", True),
                 ("cp313-abi3-manylinux2014_aarch64", "aarch64", False),
                 ("cp311-cp311-manylinux2014_aarch64", "aarch64", False),
                 ("cp312-cp312-manylinux_2_28_x86_64", "aarch64", False),
                 ("cp312-cp312-win_amd64", "x86_64", False),
                 ("cp312-cp312-linux_x86_64", "x86_64", False),
                 ("cp312-cp312-manylinux2014_x86_64", "aarch64", False),
                 ("cp312-cp312-manylinux1_x86_64", "aarch64", False),
                 ("cp312-cp312-manylinux2010_x86_64", "aarch64", False),
                 ("cp312-cp312-manylinux2014_aarch64", "x86_64", False),
                 ("cp312-cp312-manylinux2014_aarch64", "aarch64", True),
                 ("cp312-cp312-manylinux2014_x86_64", "x86_64", True),
                 ("cp312-cp312-musllinux_1_2_aarch64", "aarch64", False),
                 ("py3-none-any", "aarch64", True)]
        for suffix, machine, expected in cases:
            n = node(); n["artifacts"][0]["filename"] = "docling_slim-2.145.0-" + suffix + ".whl"
            with self.subTest(suffix=suffix):
                self.assertEqual(bool(m.wheel_candidates(n, machine)), expected)

    def test_compressed_platform_tags(self):
        n = node()
        n["artifacts"][0]["filename"] = "docling_slim-2.145.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        self.assertEqual(m.wheel_candidates(n, "aarch64"), [])
        self.assertEqual(len(m.wheel_candidates(n, "x86_64")[0]["tags"]), 2)

    def test_saved_output_and_architecture(self):
        current = m.build()
        self.assertEqual(current, json.loads((HERE / "per-platform-results.json").read_text()))
        for r in current["platforms"].values():
            self.assertEqual(sum(len(p["candidates"]) for p in r["packages"]), 57)
            for p in r["packages"]:
                for candidate in p["candidates"]:
                    for tag in candidate["tags"]:
                        self.assertTrue(tag["tag"].endswith("-any") or tag["tag"].endswith("_" + r["machine"]))

    def test_no_pseudo_ready(self):
        with self.assertRaisesRegex(ValueError, "NOT_A_LOCK"):
            m.require_real_solution(dict(status="READY_FOR_ARTIFACT_REVIEW", resolverRun="NOT_RUN", solution=[]))

    def test_profile_drift_rejected(self):
        profile = json.loads((HERE / "docling-lite-profile.json").read_text())
        m.validate_profile(profile, {"docling-slim": node()})
        for key, value in [("root", "docling==2.145.0"), ("extras", ["standard"]),
                           ("pythonPatch", "3.12.0"), ("targets", []), ("pythonMinor", "3.13")]:
            changed = copy.deepcopy(profile); changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "PROFILE_CONTRACT"):
                m.validate_profile(changed, {"docling-slim": node()})

    def test_root_version_drift_rejected(self):
        profile = json.loads((HERE / "docling-lite-profile.json").read_text())
        with self.assertRaisesRegex(ValueError, "ROOT_VERSION"):
            m.validate_profile(profile, {"docling-slim": node(version="2.144.0")})

    def test_real_snapshot_and_reproducibility(self):
        first = m.build(); self.assertEqual(first, m.build())
        self.assertEqual(first["status"], "BLOCKED_WITH_WITNESS")
        for r in first["platforms"].values():
            self.assertEqual(len(r["packages"]), 54)
            self.assertEqual(len(r["declarations"]), 79)
            self.assertEqual([(e["parent"], e["requirement"], e["observedVersion"]) for e in r["snapshotConflicts"]],
                             [("docling-core", "doclang<0.9,>=0.8", "0.9.0")])
            root = next(p for p in r["packages"] if p["name"] == "docling-slim")
            self.assertEqual(root["selectedExtras"], sorted(m.EXTRAS))
            self.assertFalse(any(p["name"] in ["torch", "paddlex", "paddleocr"] for p in r["packages"]))
            self.assertTrue(all(p["selectedWheel"] is None for p in r["packages"]))


if __name__ == "__main__":
    unittest.main()
