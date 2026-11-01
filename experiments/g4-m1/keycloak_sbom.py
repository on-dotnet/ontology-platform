#!/usr/bin/env python3
"""固定Keycloak ARM64镜像的stdlib离线部分SBOM；仅读层，不执行、不联网、不作许可裁决。"""
import argparse
import datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import struct
import tarfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

IMAGE = "sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4"
INDEX = "sha256:3f3c5f8e03c614774b4bd9173b88391fefa4153bfc010d8012d59ad825377332"
FILE_LIMIT = 200 * 1024 * 1024
TEXT_LIMIT = 2 * 1024 * 1024
TOTAL_TEXT_LIMIT = 32 * 1024 * 1024
ZIP_EXPANDED_LIMIT = 512 * 1024 * 1024
RPM_TAGS = {1000: "name", 1001: "version", 1002: "release", 1014: "license", 1022: "architecture"}


def sha(data):
    """计算原字节SHA256，不对原镜像内容写入。"""
    return hashlib.sha256(data).hexdigest()


def normalized(name):
    """只接受安全相对tar/zip路径，绝不执行extractall。"""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("UNSAFE_ARCHIVE_PATH")
    return str(path)


def blob(oci, descriptor, read=False):
    """校验所有OCI对象原摘要与声明长度；大层仅流式散列。"""
    digest = descriptor["digest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("INVALID_DIGEST")
    path = oci / "blobs" / "sha256" / digest[7:]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != descriptor["size"]:
        raise ValueError("BLOB_SIZE_OR_PATH_MISMATCH")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    if "sha256:" + hasher.hexdigest() != digest:
        raise ValueError("BLOB_DIGEST_MISMATCH")
    if read:
        if path.stat().st_size > TEXT_LIMIT:
            raise ValueError("METADATA_BUDGET")
        return path.read_bytes()
    return path


def rpm_inventory(raw, source):
    """只在内存副本改SQLite读写版本；保留原DB哈希及每个RPM头的原字段。"""
    if raw[:16] != b"SQLite format 3\x00":
        raise ValueError("INVALID_RPM_SQLITE")
    memory_copy = bytearray(raw)
    original_versions = list(memory_copy[18:20])
    memory_copy[18:20] = b"\x01\x01"
    with sqlite3.connect(":memory:") as database:
        database.deserialize(bytes(memory_copy))
        database.execute("PRAGMA query_only=ON")
        records = database.execute("SELECT hnum, blob FROM Packages ORDER BY hnum").fetchall()
    packages = []
    for hnum, header in records:
        count, size = struct.unpack_from(">II", header)
        start = 8 + count * 16
        if count > 4096 or start + size != len(header):
            raise ValueError("RPM_HEADER_BOUNDS")
        fields = {}
        for index in range(count):
            tag, kind, offset, items = struct.unpack_from(">IIII", header, 8 + index * 16)
            if tag not in RPM_TAGS:
                continue
            if kind != 6 or items != 1 or offset >= size:
                raise ValueError("RPM_FIELD_TYPE")
            end = header.find(b"\x00", start + offset, start + size)
            if end < 0:
                raise ValueError("RPM_FIELD_TERMINATOR")
            fields[RPM_TAGS[tag]] = header[start + offset:end].decode("utf-8", errors="strict")
        if fields.keys() != set(RPM_TAGS.values()):
            raise ValueError("RPM_REQUIRED_FIELD_MISSING")
        packages.append(dict(source, headerNumber=hnum, headerSha256=sha(header), rawFields=fields))
    return packages, {"originalHeaderVersions": original_versions, "inMemoryHeaderVersions": [1, 1],
                      "sourceChanged": False, "query": "SELECT hnum, blob FROM Packages ORDER BY hnum"}


def properties(text):
    """读取Maven生成的简单properties；保留原文，复杂转义不猜测坐标。"""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        match = re.match(r"([^=: ]+)\s*[=:]\s*(.*)$", line)
        if match and "\\" not in line:
            result[match[1]] = match[2]
    return result


def manifest_fields(text):
    """按JAR规范折叠续行，保留许可字段原文。"""
    fields = {}
    last = None
    for line in text.splitlines():
        if line.startswith(" ") and last is not None:
            fields[last] += line[1:]
        elif ": " in line:
            last, value = line.split(": ", 1)
            fields[last] = value
        else:
            last = None
    return fields


def license_name(path):
    """识别许可及版权通知文件，不把任意包文件视为许可。"""
    name = PurePosixPath(path).name.lower()
    if "/services/" in path.lower() or name.endswith((".class", ".jar", ".so", ".dll", ".js", ".css", ".png", ".svg")):
        return False
    return bool(re.search(r"(?:^|[-_.])(licenses?|licences?|notice|copyright|copying)(?:[._-]|$)", name)) or "/licenses/" in path.lower() or "/legal/" in path.lower()


def native_name(path):
    """索引显式原生二进制及JNI路径，不执行或加载它们。"""
    name = path.lower()
    return bool(re.search(r"\.(so(?:\.[0-9.]+)?|dll|dylib|exe|a)$", name)) or "/native/" in name


class Inventory:
    """在明确内存/文本预算内保存原来源与覆盖缺口。"""

    def __init__(self):
        self.texts = {}
        self.text_bytes = 0
        self.gaps = []
        self.jars = {}
        self.native = {}
        self.outer_licenses = {}
        self.file_kinds = {}
        self.rpm_db = None
        self.rpm_wal = None

    def text(self, data, source, kind):
        """以原字节摘要去重文本；每个原来源仍保留独立引用。"""
        digest = sha(data)
        record = dict(source, kind=kind, sizeBytes=len(data), sha256=digest)
        if len(data) > TEXT_LIMIT:
            self.gaps.append(dict(record, reason="TEXT_OVER_2_MIB"))
            return dict(record, textSha256=None)
        if digest not in self.texts:
            if self.text_bytes + len(data) > TOTAL_TEXT_LIMIT:
                self.gaps.append(dict(record, reason="TEXT_TOTAL_OVER_32_MIB"))
                return dict(record, textSha256=None)
            decoded = data.decode("utf-8", errors="replace")
            self.texts[digest] = {"sizeBytes": len(data), "text": decoded,
                                  "encoding": "UTF-8", "replacementCharacters": decoded.count("\ufffd")}
            self.text_bytes += len(data)
        return dict(record, textSha256=digest)

    def jar(self, data, source):
        """仅读有界ZIP条目；物理JAR与其多个Maven坐标分列计数。"""
        result = dict(source, mavenCoordinates=[], pomLicenses=[], bundleLicense=[], licenseNoticeFiles=[],
                      nativeBinaries=[], compiledJavaScript=[], embeddedPackageJson=[], nestedJars=[])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(entry.file_size for entry in entries) > ZIP_EXPANDED_LIMIT:
                raise ValueError("JAR_EXPANSION_BUDGET")
            if len({entry.filename for entry in entries}) != len(entries):
                raise ValueError("DUPLICATE_JAR_ENTRY")
            for entry in entries:
                name = normalized(entry.filename)
                if entry.is_dir():
                    continue
                inner = dict(source, entryPath=name)
                if entry.file_size > FILE_LIMIT:
                    self.gaps.append(dict(inner, sizeBytes=entry.file_size, reason="ZIP_FILE_OVER_200_MIB"))
                    continue
                if name.lower().endswith(".jar"):
                    result["nestedJars"].append(dict(inner, sizeBytes=entry.file_size))
                    self.gaps.append(dict(inner, reason="NESTED_JAR_NOT_SCANNED"))
                is_text = name.endswith(("pom.properties", "pom.xml")) or name.upper() == "META-INF/MANIFEST.MF" or license_name(name) or PurePosixPath(name).name == "package.json"
                is_native = native_name(name)
                is_js = name.endswith((".js", ".mjs", ".cjs"))
                if not (is_text or is_native or is_js):
                    continue
                if is_text and entry.file_size > TEXT_LIMIT:
                    self.gaps.append(dict(inner, sizeBytes=entry.file_size, reason="TEXT_OVER_2_MIB_NOT_READ"))
                    continue
                raw = archive.read(entry)
                inner.update(sizeBytes=len(raw), entrySha256=sha(raw))
                if is_native:
                    result["nativeBinaries"].append(dict(inner, format="ELF" if raw[:4] == b"\x7fELF" else "OPAQUE_NATIVE_CANDIDATE", licenseCoverage="NOT_VERIFIED"))
                if is_js:
                    result["compiledJavaScript"].append(inner)
                if not is_text:
                    continue
                text = raw.decode("utf-8", errors="replace")
                if name.endswith("pom.properties"):
                    fields = properties(text)
                    record = dict(inner, rawFields=fields, evidence=self.text(raw, inner, "pom.properties"))
                    if all(fields.get(key) for key in ("groupId", "artifactId", "version")):
                        record["purl"] = "pkg:maven/" + urllib.parse.quote(fields["groupId"], safe=".") + "/" + urllib.parse.quote(fields["artifactId"], safe="") + "@" + urllib.parse.quote(fields["version"], safe="")
                    else:
                        self.gaps.append(dict(inner, reason="POM_PROPERTIES_COORDINATES_INCOMPLETE"))
                    result["mavenCoordinates"].append(record)
                elif name.endswith("pom.xml"):
                    licenses = []
                    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
                        self.gaps.append(dict(inner, reason="XML_ENTITY_DECLARATION_REFUSED"))
                    else:
                        try:
                            pom = ET.fromstring(raw)
                            for item in pom.findall("{*}licenses/{*}license"):
                                licenses.append({PurePosixPath(child.tag.split("}")[-1]).name: child.text or "" for child in item})
                        except ET.ParseError:
                            self.gaps.append(dict(inner, reason="POM_XML_PARSE_FAILED"))
                    result["pomLicenses"].append(dict(inner, licenses=licenses, evidence=self.text(raw, inner, "pom.xml"), inheritedLicenseResolution="NOT_PERFORMED"))
                elif name.upper() == "META-INF/MANIFEST.MF":
                    fields = manifest_fields(text)
                    if "Bundle-License" in fields:
                        result["bundleLicense"].append(dict(inner, rawValue=fields["Bundle-License"], evidence=self.text(raw, inner, "MANIFEST.MF")))
                elif PurePosixPath(name).name == "package.json":
                    result["embeddedPackageJson"].append(self.text(raw, inner, "package.json"))
                if license_name(name):
                    result["licenseNoticeFiles"].append(self.text(raw, inner, "LICENSE_NOTICE_COPYRIGHT"))
        if not result["mavenCoordinates"]:
            result["identityCoverage"] = "FILENAME_ONLY_NO_POM_PROPERTIES"
        if result["compiledJavaScript"]:
            self.gaps.append(dict(source, reason="COMPILED_JS_TRANSITIVE_DEPENDENCIES_NOT_INVENTORIED", compiledJavaScriptFiles=len(result["compiledJavaScript"]), embeddedPackageJsonFiles=len(result["embeddedPackageJson"])))
        return result

    def layer(self, path, digest):
        """流式只读tar，最终路径覆盖旧层；本固定镜像若出现whiteout即拒绝。"""
        with tarfile.open(path, "r|gz") as archive:
            for member in archive:
                name = normalized(member.name)
                if PurePosixPath(name).name.startswith(".wh."):
                    raise ValueError("UNEXPECTED_WHITEOUT_REFUSED")
                self.file_kinds[name] = "regular" if member.isfile() else "nonregular"
                for collection in (self.jars, self.native, self.outer_licenses):
                    collection.pop(name, None)
                if not member.isfile():
                    continue
                source = {"imageDigest": IMAGE, "layerDigest": digest, "path": name, "sizeBytes": member.size}
                if member.size > FILE_LIMIT:
                    self.gaps.append(dict(source, reason="TAR_FILE_OVER_200_MIB"))
                    continue
                stream = archive.extractfile(member)
                prefix = stream.read(4)
                is_db = name == "var/lib/rpm/rpmdb.sqlite"
                is_wal = name == "var/lib/rpm/rpmdb.sqlite-wal"
                is_jar = name.lower().endswith(".jar")
                is_license = license_name(name)
                is_native = prefix == b"\x7fELF" or native_name(name)
                if not (is_db or is_wal or is_jar or is_license or is_native):
                    continue
                if is_license and member.size > TEXT_LIMIT and not (is_jar or is_db or is_native):
                    self.gaps.append(dict(source, reason="TEXT_OVER_2_MIB_NOT_READ"))
                    continue
                data = prefix + stream.read(FILE_LIMIT + 1 - len(prefix))
                if len(data) != member.size:
                    raise ValueError("TAR_SIZE_MISMATCH")
                source["fileSha256"] = sha(data)
                if is_db:
                    self.rpm_db = (data, source)
                if is_wal:
                    self.rpm_wal = source
                    if data:
                        raise ValueError("RPM_WAL_NONEMPTY_REFUSED")
                if is_jar:
                    self.jars[name] = self.jar(data, source)
                if is_license:
                    self.outer_licenses[name] = self.text(data, source, "OUTER_LICENSE_NOTICE_COPYRIGHT")
                if is_native:
                    self.native[name] = dict(source, format="ELF" if prefix == b"\x7fELF" else "OPAQUE_NATIVE_CANDIDATE", licenseCoverage="RPM_OR_EMBEDDED_TEXT_MAPPING_PARTIAL")


def generate(oci, output):
    """只接受固定获批ARM64对象，输出SPDX2.3和带原字段/原文的部分覆盖报告。"""
    oci = oci.resolve(strict=True)
    index = json.loads((oci / "index.json").read_text())
    if len(index["manifests"]) != 1 or index["manifests"][0]["digest"] != IMAGE:
        raise ValueError("FIXED_PLATFORM_REQUIRED")
    manifest = json.loads(blob(oci, index["manifests"][0], read=True))
    official = (oci / "official-index.json").read_bytes()
    if "sha256:" + sha(official) != INDEX:
        raise ValueError("OFFICIAL_INDEX_MISMATCH")
    if not any(item["digest"] == IMAGE and item.get("platform", {}).get("architecture") == "arm64" and item.get("platform", {}).get("os") == "linux" for item in json.loads(official)["manifests"]):
        raise ValueError("OFFICIAL_PLATFORM_BINDING_MISMATCH")
    config = json.loads(blob(oci, manifest["config"], read=True))
    if config["architecture"] != "arm64" or config["os"] != "linux" or len(manifest["layers"]) != 4:
        raise ValueError("PLATFORM_OR_LAYER_COUNT_MISMATCH")
    inventory = Inventory()
    for descriptor in manifest["layers"]:
        inventory.layer(blob(oci, descriptor), descriptor["digest"])
    if inventory.rpm_db is None:
        raise ValueError("RPM_DATABASE_REQUIRED")
    rpms, sqlite_method = rpm_inventory(*inventory.rpm_db)
    jars = [inventory.jars[path] for path in sorted(inventory.jars)]
    counts = {"rpmPackages": len(rpms), "physicalJarFiles": len(jars),
              "jarsWithPomProperties": sum(bool(jar["mavenCoordinates"]) for jar in jars),
              "filenameOnlyJars": sum(not jar["mavenCoordinates"] for jar in jars),
              "jarsWithoutEmbeddedLicenseEvidence": sum(not jar["licenseNoticeFiles"] and not jar["bundleLicense"] and not any(pom["licenses"] for pom in jar["pomLicenses"]) for jar in jars),
              "mavenCoordinateRecords": sum(len(jar["mavenCoordinates"]) for jar in jars),
              "pomXmlEntries": sum(len(jar["pomLicenses"]) for jar in jars),
              "jarsWithPomXml": sum(bool(jar["pomLicenses"]) for jar in jars),
              "jarsWithBundleLicense": sum(bool(jar["bundleLicense"]) for jar in jars),
              "jarsWithLicenseNoticeFiles": sum(bool(jar["licenseNoticeFiles"]) for jar in jars),
              "outerNativeBinaries": len(inventory.native),
              "embeddedNativeCandidates": sum(len(jar["nativeBinaries"]) for jar in jars),
              "compiledJavaScriptEntries": sum(len(jar["compiledJavaScript"]) for jar in jars),
              "deduplicatedTextBytes": inventory.text_bytes}
    gaps = [{"reason": "MANUAL_OFFLINE_PARTIAL", "details": "RPM44 and physical JAR487 are separate inventories; Maven coordinates overlap physical JARs and are not additional installed-package totals. No executable scanner, vulnerability database, signature verification or legal verdict was run."},
            {"reason": "JS_BUNDLES_NOT_FULL_PACKAGE_INVENTORY", "details": "Keycloak themes/vendor/admin/account and Quarkus UI compiled JavaScript may contain transitive packages without package.json. Maven coordinates and JAR notices do not prove those dependencies fully covered."},
            {"reason": "JDK_MODULES_AND_NATIVE_COVERAGE_PARTIAL", "details": "JDK modular runtime and native ELF/JNI files are indexed but RPM/component-to-license mapping is not exhaustive. Filename-only JARs and inherited POM license declarations require independent review."}]
    report = {"schemaVersion": 1, "taskId": "G4-M1-RECOVERY-001", "status": "MANUAL_OFFLINE_PARTIAL",
              "imageDigest": IMAGE, "officialIndexDigest": INDEX, "platform": "linux/arm64", "layers": manifest["layers"],
              "method": {"tool": "Python stdlib tarfile/zipfile/sqlite3/xml", "generatorSha256": sha(Path(__file__).read_bytes()),
                         "containerExecution": False, "networkRequests": 0, "sourceMutation": False,
                         "sqlite": sqlite_method, "rpmWal": inventory.rpm_wal,
                         "limits": {"singleFileBytes": FILE_LIMIT, "singleTextBytes": TEXT_LIMIT, "totalTextBytes": TOTAL_TEXT_LIMIT, "jarExpandedBytes": ZIP_EXPANDED_LIMIT}},
              "counts": counts, "rpmPackages": rpms, "jarArtifacts": jars,
              "outerLicenseFiles": list(inventory.outer_licenses.values()), "outerNativeBinaries": list(inventory.native.values()),
              "textPayloadsBySha256": inventory.texts, "coverageGaps": gaps + inventory.gaps,
              "licenseVerdict": "NOT_VERIFIED_REQUIRES_NON_AUTHOR_REVIEW", "cveStatus": "NOT_VERIFIED", "signatureStatus": "NOT_VERIFIED"}
    packages = [{"SPDXID": "SPDXRef-Image", "name": "quay.io/keycloak/keycloak", "versionInfo": "26.8.1", "downloadLocation": "https://quay.io/v2/keycloak/keycloak/manifests/" + IMAGE,
                 "filesAnalyzed": False, "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION",
                 "checksums": [{"algorithm": "SHA256", "checksumValue": IMAGE[7:]}], "sourceInfo": "Fixed linux/arm64 OCI manifest; MANUAL_OFFLINE_PARTIAL; see 1-manual-licenses.json."}]
    for position, rpm in enumerate(rpms):
        fields = rpm["rawFields"]
        packages.append({"SPDXID": "SPDXRef-Rpm-" + str(position), "name": fields["name"], "versionInfo": fields["version"] + "-" + fields["release"], "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                         "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION",
                         "sourceInfo": json.dumps({key: rpm[key] for key in ("imageDigest", "layerDigest", "path", "fileSha256", "headerNumber", "headerSha256")}, sort_keys=True),
                         "licenseComments": "Original RPM License field (not normalized or adjudicated): " + fields["license"]})
    for position, jar in enumerate(jars):
        package = {"SPDXID": "SPDXRef-Jar-" + str(position), "name": PurePosixPath(jar["path"]).name, "packageFileName": jar["path"], "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                   "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION", "checksums": [{"algorithm": "SHA256", "checksumValue": jar["fileSha256"]}],
                   "sourceInfo": json.dumps({key: jar[key] for key in ("imageDigest", "layerDigest", "path", "fileSha256")}, sort_keys=True),
                   "licenseComments": "Raw embedded POM/Bundle-License/LICENSE/NOTICE and coverage gaps are in 1-manual-licenses.json; no automatic license verdict."}
        references = sorted({item["purl"] for item in jar["mavenCoordinates"] if "purl" in item})
        if len(references) == 1:
            package["externalRefs"] = [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": references[0]}]
        elif references:
            package["comment"] = "Multiple embedded Maven coordinates are retained in the companion report; they describe bundled components and are not all asserted as identities of this physical JAR."
        packages.append(package)
    relationships = [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Image"}]
    relationships.extend({"spdxElementId": "SPDXRef-Image", "relationshipType": "CONTAINS", "relatedSpdxElement": package["SPDXID"]} for package in packages[1:])
    sbom = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT", "name": "Keycloak-26.8.1-linux-arm64-MANUAL-OFFLINE-PARTIAL",
            "documentNamespace": "https://ontology-platform.invalid/spdx/keycloak/" + IMAGE[7:],
            "creationInfo": {"created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "creators": ["Tool: keycloak_sbom.py-1.0"], "comment": "MANUAL_OFFLINE_PARTIAL; no legal, CVE or signature verdict; no container execution."},
            "comment": "44 RPM records plus 487 physical JAR artifacts; Maven coordinates overlap JAR artifacts; multi-coordinate bundled JARs are not assigned multiple identity externalRefs. Coordinates are not an extra package total. Compiled JS/JDK/native coverage gaps retained in companion report.",
            "packages": packages, "relationships": relationships}
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("OUTPUT_SYMLINK_REFUSED")
    summary = {"status": "MANUAL_OFFLINE_PARTIAL", "counts": counts, "outputs": {}}
    for name, value in (("1-manual-sbom.json", sbom), ("1-manual-licenses.json", report)):
        data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        with (output / name).open("xb") as stream:
            stream.write(data)
        summary["outputs"][name] = {"sizeBytes": len(data), "sha256": sha(data)}
    return summary


def main():
    """显式输入输出路径；失败关闭，不安装工具、不运行镜像或调用网络。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oci-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.oci_dir, args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
