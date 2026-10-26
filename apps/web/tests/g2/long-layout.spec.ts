import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { OntologyDraft, RdfTerm, RdfTriple, SemanticNode, SourceBundle, SourceHashes } from "../../src/lib/api/g2-generated";
const rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
const rdfs = "http://www.w3.org/2000/01/rdf-schema#";
const owl = "http://www.w3.org/2002/07/owl#";
const ex = "urn:synthetic:metals:";
const op = "urn:ontology-platform:vocabulary:";
const addedIri = "urn:synthetic:Class:7722bc0a-2a53-4440-b823-1e0a61f843c8";
const digest = (value: string) => createHash("sha256").update(value, "utf8").digest("hex");
const iri = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const triple = (subject: string, predicate: string, object: string): RdfTriple => ({ subject: iri(subject), predicate, object: iri(object) });
/** 仅有界UI夹具：标准五类/四关系/五数据属性共27条IRI断言；新增Class后28条，不在产品内解析或重建OWL。 */
function fixture(revision: number, added: boolean): OntologyDraft {
  const triples = ["Heat", "CastingSequence", "Slab", "RollingEvent", "Coil"].map(name => triple(ex + name, rdf + "type", owl + "Class"));
  const nodes: SemanticNode[] = ["Heat", "CastingSequence", "Slab", "RollingEvent", "Coil"].map(name => ({ id: ex + name, label: ex + name, kind: "class", typeIris: [owl + "Class"] }));
  for (const [name, domain, range] of [["castIn", "Heat", "CastingSequence"], ["producesSlab", "CastingSequence", "Slab"], ["rolledIn", "Slab", "RollingEvent"], ["producesCoil", "RollingEvent", "Coil"]]) {
    triples.push(triple(ex + name, rdf + "type", owl + "ObjectProperty"), triple(ex + name, rdfs + "domain", ex + domain), triple(ex + name, rdfs + "range", ex + range));
    nodes.push({ id: ex + name, label: ex + name, kind: "objectProperty", typeIris: [owl + "ObjectProperty"] });
  }
  for (const [name, range] of [["externalId", "string"], ["organizationId", "string"], ["siteId", "string"], ["synthetic", "boolean"], ["weight", "decimal"]]) {
    triples.push(triple(op + name, rdf + "type", owl + "DatatypeProperty"), triple(op + name, rdfs + "range", "http://www.w3.org/2001/XMLSchema#" + range));
    nodes.push({ id: op + name, label: op + name, kind: "datatypeProperty", typeIris: [owl + "DatatypeProperty"] });
  }
  if (added) { triples.push(triple(addedIri, rdf + "type", owl + "Class")); nodes.push({ id: addedIri, label: addedIri, kind: "class", typeIris: [owl + "Class"] }); }
  const sources: SourceBundle = { ontologyTurtle: "# Synthetic bounded layout fixture\n" + triples.map(item => `<${item.subject.value}> <${item.predicate}> <${item.object.value}> .`).join("\n") + "\n", shapesTurtle: readFileSync(resolve("../../samples/g2/shapes.ttl"), "utf8"), vocabularyTurtle: readFileSync(resolve("../../samples/g2/vocabulary.ttl"), "utf8"), dataTurtle: readFileSync(resolve("../../samples/g2/data.ttl"), "utf8") };
  const hashes: SourceHashes = { ontologyHash: digest(sources.ontologyTurtle), shapesHash: digest(sources.shapesTurtle), vocabularyHash: digest(sources.vocabularyTurtle!), dataHash: digest(sources.dataTurtle), bundleHash: "" };
  hashes.bundleHash = digest([hashes.ontologyHash, hashes.shapesHash, hashes.vocabularyHash, hashes.dataHash].join("\n"));
  return { draftId: "draft-layout", assetId: "asset-layout", scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, baseReleaseId: null, revision, etag: `"${revision}"`, name: "Synthetic 长IRI真实规模草稿", sources, hashes, ownerSubjectId: "g2-ui-fixture", updatedAtUtc: "2026-10-26T00:00:00Z", projection: { revision, hashes, triples, nodes, edges: triples.map(item => ({ id: digest(JSON.stringify(item)), source: item.subject.value, predicateIri: item.predicate, target: item.object.value, label: item.predicate })), structuralEditAllowed: true, diagnostics: [] } };
}
test("真实规模长IRI/28三元组/SHACL/Diff在1440/1280/390深浅主题不撑开面板", async ({ page }) => {
  const initial = fixture(2, false); const updated = fixture(3, true); let writes = 0;
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message)); page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.route("**/auth/csrf", route => route.fulfill({ json: { requestToken: "bounded-ui" } }));
  await page.route("**/api/v1/ontology-drafts", route => route.fulfill({ json: [initial] }));
  await page.route("**/api/v1/ontology-drafts/draft-layout", route => route.fulfill({ json: initial }));
  await page.route("**/api/v1/ontology-drafts/draft-layout/edits", route => { writes++; return route.fulfill({ json: updated }); });
  await page.route("**/api/v1/ontology-drafts/draft-layout/validations", route => { writes++; return route.fulfill({ json: { reportId: "report-layout", draftId: updated.draftId, revision: 3, hashes: updated.hashes, kind: "SHACL_CORE", conforms: true, issues: [], rawReportHash: digest("bounded report"), validatedAtUtc: "2026-10-26T00:00:00Z", traceId: "bounded-layout-trace" } }); });
  await page.route("**/api/v1/ontology-drafts/draft-layout/diff?*", route => route.fulfill({ json: { baseRevision: 1, targetRevision: 3, baseHashes: initial.hashes, targetHashes: updated.hashes, addedTriples: [updated.projection.triples.at(-1)], removedTriples: [], sourceDiff: JSON.stringify({ before: initial.sources, after: updated.sources }), unsupportedDiagnostics: [] } }));
  await page.setViewportSize({ width: 1280, height: 1000 }); await page.goto("/ontologies"); await page.getByRole("button", { name: /Synthetic 长IRI真实规模草稿/ }).click();
  await expect(page.locator(".g2-graph canvas").first()).toBeVisible();
  await page.getByRole("textbox", { name: "变更理由" }).fill("Synthetic 长IRI布局回归");
  await page.evaluate(() => new Promise<void>(resolveFrame => requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()))));
  const initialLayout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, inspectorWidth: document.querySelector(".g2-inspector")!.getBoundingClientRect().width, children: Array.from(document.querySelector(".g2-inspector")!.children).map(item => ({ tag: item.tagName, width: item.getBoundingClientRect().width, right: item.getBoundingClientRect().right })) }));
  writeFileSync(resolve("../../docs/evidence/G2-THIN-SLICE-001/FE/logs/long-layout-initial-1280.json"), JSON.stringify(initialLayout, null, 2) + "\n");
  expect(initialLayout.scrollWidth).toBeLessThanOrEqual(initialLayout.width);
  await page.getByRole("textbox", { name: "变更理由" }).fill("Synthetic 长IRI布局回归");
  await page.getByRole("combobox", { name: "结构操作" }).selectOption("add"); await page.getByRole("textbox", { name: "主体IRI" }).fill(addedIri); await page.getByRole("combobox", { name: "标准声明快捷填入" }).selectOption(owl + "Class"); await page.getByRole("button", { name: "提交真实结构编辑" }).click();
  await expect(page.getByText("revision 3 · 15 节点 / 28 关系")).toBeVisible();
  await page.getByRole("button", { name: "验证已保存修订" }).click(); await expect(page.getByText("SHACL_CORE · 符合 · revision 3")).toBeVisible();
  await page.getByRole("button", { name: "读取真实 Diff" }).click(); await expect(page.getByText("revision 1 → 3 · +1 / −0 triples")).toBeVisible();
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: 1000 }); if (width === 390) await page.getByRole("button", { name: "图与校验", exact: true }).click();
    for (const theme of ["dark", "light"]) {
      if (await page.locator("html").getAttribute("data-theme") !== theme) await page.getByRole("button", { name: "切换深浅主题" }).click();
      await page.evaluate(() => new Promise<void>(resolveFrame => requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()))));
      const measured = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, inspectorWidth: document.querySelector(".g2-inspector")!.getBoundingClientRect().width, children: Array.from(document.querySelector(".g2-inspector")!.children).map(item => ({ tag: item.tagName, width: item.getBoundingClientRect().width, right: item.getBoundingClientRect().right })) }));
      writeFileSync(resolve(`../../docs/evidence/G2-THIN-SLICE-001/FE/logs/long-layout-${width}-${theme}-observed.json`), JSON.stringify(measured, null, 2) + "\n");
      if (measured.scrollWidth > width) await page.screenshot({ path: `../../docs/evidence/G2-THIN-SLICE-001/FE/screenshots/long-layout-${width}-${theme}-red.png`, fullPage: true, animations: "disabled" });
      expect(measured.scrollWidth).toBeLessThanOrEqual(width);
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect.poll(() => page.locator(".g2-graph").evaluate(element => { const canvas = element.querySelector("canvas"); return !!canvas && canvas.getBoundingClientRect().width <= element.getBoundingClientRect().width && canvas.getBoundingClientRect().width >= element.clientWidth - 2; })).toBe(true);
      const details = page.locator(".g2-inspector details"); if (!await details.evaluate(element => (element as HTMLDetailsElement).open)) { await details.locator("summary").focus(); await page.keyboard.press("Enter"); }
      const node = page.getByRole("button", { name: addedIri, exact: true }); await node.focus(); await expect(node).toBeFocused(); await page.keyboard.press("Enter");
      await expect(page.getByRole("textbox", { name: "主体IRI" })).toHaveValue(addedIri);
      await expect(page.locator(".g2-inspector p.g2-hash").first()).toHaveText(addedIri);
      expect(await page.locator(".g2-inspector").evaluate(element => ["hidden", "clip"].includes(getComputedStyle(element).overflowX))).toBe(false);
      expect(await page.locator(".g2-inspector .g2-pre").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      await page.getByRole("button", { name: "重新布局" }).focus(); await page.keyboard.press("Enter"); await expect(page.getByText("revision 3 · 15 节点 / 28 关系")).toBeVisible();
      await expect.poll(() => page.locator(".g2-graph").evaluate(element => { const canvas = element.querySelector("canvas"); return !!canvas && canvas.getBoundingClientRect().width <= element.getBoundingClientRect().width && canvas.getBoundingClientRect().width >= element.clientWidth - 2; })).toBe(true);
      await expect.poll(() => page.locator(".g2-inspector").evaluate(element => { const right = element.getBoundingClientRect().right; return Array.from(element.children).every(child => child.getBoundingClientRect().right <= right + 1); })).toBe(true);
      await page.screenshot({ path: `../../docs/evidence/G2-THIN-SLICE-001/FE/screenshots/long-layout-${width}-${theme}.png`, fullPage: true, animations: "disabled" });
    }
  }
  expect(writes).toBe(2); expect(errors).toEqual([]);
});
