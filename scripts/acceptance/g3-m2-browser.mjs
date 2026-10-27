/** M2只消费既有真实OIDC上下文，记录精确编辑、诊断和发布回滚的可复验事实。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { evidenceDirectory } from "./evidence-paths.mjs";
import { fullChain } from "./g2-full-chain.mjs";

const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const rdfs = "http://www.w3.org/2000/01/rdf-schema#";
const owl = "http://www.w3.org/2002/07/owl#";

/** 每次从真实API创建独立合成资产，不能消费旧轮成功文件。 */
export async function runM2Checks(context) {
  const { root, origin, operator, viewer, single, command, setPhase } = context;
  const checks = [];
  const evidence = evidenceDirectory(root);
  const startedAtUtc = new Date().toISOString();
  let phase = "profile";
  let status = "FAIL";
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    context.check("m2_" + name, condition, observedStatus);
  };
  const step = name => { phase = name; setPhase("m2_" + name); };
  async function post(user, path, data, expected = 200, match = true) {
    const response = await user.api.post(origin + path, { data, headers: {
      ...user.headers, ...(match && data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}),
    } });
    observe("http_" + checks.length, response.status() === expected, response.status());
    return response.json();
  }
  async function openDraft(page, name) {
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic M2 exact edit acceptance");
  }
  try {
    const profile = await (await viewer.api.get(origin + "/api/v1/semantic/support-profile")).json();
    observe("current_profile_v2", profile.version === "2" && profile.reasoningMode === "ASSERTED_ONLY"
      && profile.capabilities.slice(8, 11).every(row => row.edit === "BASIC"));
    const sources = {};
    for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"],
      ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
      sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
    }
    const name = "Synthetic M2 modeler " + randomUUID().slice(0, 8);
    let draft = await post(operator, "/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) });
    const editsPath = "/api/v1/ontology-drafts/" + draft.draftId + "/edits";
    const intent = { subjectIri: "urn:synthetic:metals:Heat", predicateIri: rdfs + "comment", oldObject: null,
      newObject: { kind: "literal", value: "Synthetic M2", datatype: null, language: "zh" } };
    step("http_negative_boundaries");
    await post(operator, editsPath, { edit: intent, command: command(draft.revision) }, 428, false);
    await post(operator, editsPath, { edit: intent, command: command(draft.revision - 1) }, 409);
    await post(operator, editsPath, { edit: { ...intent, actor: "forged" }, command: command(draft.revision) }, 400);
    await post(viewer, editsPath, { edit: intent, command: command(draft.revision) }, 403);
    await post(single, editsPath, { edit: intent, command: command(draft.revision) }, 403);
    const before = draft;
    const unchanged = await (await operator.api.get(origin + "/api/v1/ontology-drafts/" + draft.draftId)).json();
    observe("rejections_preserve_revision_hash", unchanged.revision === before.revision && unchanged.hashes.bundleHash === before.hashes.bundleHash);
    if (context.apiOnly) {
      step("real_api_edit_assessment");
      draft = await post(operator, editsPath, { edit: {
        subjectIri: "urn:synthetic:metals:Heat", predicateIri: owl + "equivalentClass", oldObject: null,
        newObject: { kind: "iri", value: "urn:synthetic:metals:Coil", datatype: null, language: null },
      }, command: command(draft.revision) });
      observe("api_named_edit_persisted", draft.revision === before.revision + 1 && draft.projection.triples.some(row =>
        row.subject.value === "urn:synthetic:metals:Heat" && row.predicate === owl + "equivalentClass"));
      observe("api_other_sources_exact", ["shapesTurtle", "vocabularyTurtle", "dataTurtle"].every(key => draft.sources[key] === sources[key]));
      const assessed = await post(operator, "/api/v1/ontology-drafts/" + draft.draftId + "/assessments", {
        revision: draft.revision, hashes: draft.hashes, command: command(draft.revision),
      });
      observe("api_real_assessment_current_bound", assessed.publishEligible && assessed.profileVersion === "2"
        && assessed.revision === draft.revision && assessed.hashes.bundleHash === draft.hashes.bundleHash
        && assessed.stages.some(row => row.name === "SHACL_CORE" && row.status === "PASS")
        && assessed.stages.some(row => row.name === "OWL_REASONING" && row.status === "NOT_RUN"));
      const read = await (await operator.api.get(origin + "/api/v1/ontology-drafts/" + draft.draftId)).json();
      observe("api_real_pg_revision_read", read.revision === draft.revision && read.hashes.bundleHash === draft.hashes.bundleHash);
      status = "PASS";
      return;
    }
    step("ui_exact_edit");
    const page = operator.page;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openDraft(page, name);
    const extra = "urn:synthetic:m2:" + randomUUID();
    async function submitEdit() {
      const waiting = page.waitForResponse(value => value.url() === origin + editsPath && value.request().method() === "POST");
      await page.getByRole("button", { name: "提交真实结构编辑", exact: true }).click();
      const response = await waiting;
      observe("ui_edit_http_" + checks.length, response.status() === 200, response.status());
      draft = await response.json();
      await page.getByRole("button", { name: "提交真实结构编辑", exact: true }).waitFor();
      return draft;
    }
    await page.getByRole("combobox", { name: "结构操作", exact: true }).selectOption("add");
    await page.getByRole("textbox", { name: "主体IRI", exact: true }).fill(extra);
    await page.getByRole("combobox", { name: "结构谓词", exact: true }).selectOption(rdfType);
    await page.getByRole("combobox", { name: "新对象类型", exact: true }).selectOption("iri");
    await page.getByRole("textbox", { name: "新对象值", exact: true }).fill(owl + "Class");
    await submitEdit();
    observe("ui_class_saved_as_real_triple", draft.projection.triples.some(row => row.subject.value === extra && row.predicate === rdfType && row.object.value === owl + "Class"));
    await page.getByRole("combobox", { name: "结构操作", exact: true }).selectOption("add");
    await page.getByRole("combobox", { name: "结构谓词", exact: true }).selectOption(owl + "equivalentClass");
    await page.getByRole("combobox", { name: "主体IRI", exact: true }).selectOption("urn:synthetic:metals:Heat");
    await page.getByRole("combobox", { name: "新对象值", exact: true }).selectOption(extra);
    await submitEdit();
    observe("ui_named_axiom_saved", draft.projection.triples.some(row => row.subject.value === "urn:synthetic:metals:Heat"
      && row.predicate === owl + "equivalentClass" && row.object.value === extra));
    observe("other_three_sources_exact", ["shapesTurtle", "vocabularyTurtle", "dataTurtle"].every(key => draft.sources[key] === sources[key]));
    const persisted = await (await operator.api.get(origin + "/api/v1/ontology-drafts/" + draft.draftId)).json();
    observe("ui_edits_persist_after_read", persisted.revision === draft.revision && persisted.hashes.bundleHash === draft.hashes.bundleHash);
    await page.getByRole("region", { name: "本体实体树", exact: true }).waitFor();
    const treeNode = page.getByRole("region", { name: "本体实体树", exact: true }).getByRole("button", { name: "炉次", exact: true });
    await treeNode.focus();
    await page.keyboard.press("Enter");
    observe("tree_keyboard_select", await treeNode.getAttribute("aria-pressed") === "true");
    await page.getByRole("button", { name: "图视图", exact: true }).click();
    await page.locator(".g2-graph canvas").first().waitFor();
    await mkdir(resolve(evidence, "screenshots"), { recursive: true });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      if (width === 390) await page.getByRole("button", { name: "图与校验", exact: true }).click();
      for (const theme of ["dark", "light"]) {
        if (await page.evaluate(() => document.documentElement.dataset.theme ?? "dark") !== theme) {
          await page.getByRole("button", { name: "切换深浅主题", exact: true }).click();
        }
        observe("layout_" + width + "_" + theme, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: resolve(evidence, "screenshots/m2-modeler-" + width + "-" + theme + ".png"), fullPage: true, animations: "disabled" });
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (context.uiOnly) { status = "PASS"; return; }
    step("edited_asset_publish_query_rollback");
    // 同一编辑后的资产复用既有异人审批/正式RustFS/Jena/查询/Run/SSE/回滚链，非另一套服务。
    await fullChain({ ...context, draft, check: observe, setPhase: step });
    step("shape_and_complex_diagnostics");
    const shapeSources = {
      ontologyTurtle: "<urn:m2:C> a <" + owl + "Class> .\n",
      shapesTurtle: "@prefix sh: <http://www.w3.org/ns/shacl#> . <urn:m2:S> a sh:NodeShape; sh:targetClass <urn:m2:C>; sh:property <urn:m2:P> . <urn:m2:P> a sh:PropertyShape; sh:path <urn:m2:p>; sh:minCount 1 .\n",
      vocabularyTurtle: null, dataTurtle: "<urn:m2:x> a <urn:m2:C> .\n",
    };
    const diagnosticName = "Synthetic M2 diagnostic " + randomUUID().slice(0, 8);
    const diagnosticDraft = await post(operator, "/api/v1/ontology-drafts", { name: diagnosticName, sources: shapeSources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) });
    const assessment = await post(operator, "/api/v1/ontology-drafts/" + diagnosticDraft.draftId + "/assessments", {
      revision: diagnosticDraft.revision, hashes: diagnosticDraft.hashes, command: command(diagnosticDraft.revision),
    });
    observe("real_shacl_has_shape_and_no_reasoning", !assessment.publishEligible
      && assessment.diagnostics.some(row => row.sourceShape?.value === "urn:m2:P")
      && assessment.stages.some(row => row.name === "SHACL_CORE" && row.status === "FAIL")
      && assessment.stages.some(row => row.name === "OWL_REASONING" && row.status === "NOT_RUN"));
    await openDraft(page, diagnosticName);
    const waiting = page.waitForResponse(value => value.url().endsWith("/" + diagnosticDraft.draftId + "/assessments"));
    await page.getByRole("button", { name: "评估发布资格", exact: true }).click();
    observe("ui_real_diagnostic_assessment", (await waiting).status() === 200);
    await page.getByText("urn:m2:P", { exact: false }).first().waitFor();
    const complexSources = { ...sources, ontologyTurtle: sources.ontologyTurtle
      + "\n<urn:m2:Complex> a <" + owl + "Class>; <" + rdfs + "subClassOf> [ a <" + owl + "Restriction>; <" + owl + "onProperty> <urn:synthetic:metals:castIn>; <" + owl + "someValuesFrom> <urn:synthetic:metals:Heat> ] .\n" };
    const complexName = "Synthetic M2 preserved " + randomUUID().slice(0, 8);
    const complex = await post(operator, "/api/v1/ontology-drafts", { name: complexName, sources: complexSources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) });
    observe("complex_projection_readonly", !complex.projection.structuralEditAllowed && complex.sources.ontologyTurtle === complexSources.ontologyTurtle);
    await post(operator, "/api/v1/ontology-drafts/" + complex.draftId + "/edits", { edit: intent, command: command(complex.revision) }, 422);
    const preserved = await (await operator.api.get(origin + "/api/v1/ontology-drafts/" + complex.draftId)).json();
    observe("complex_failed_edit_preserves_all_bytes", preserved.revision === complex.revision && JSON.stringify(preserved.sources) === JSON.stringify(complex.sources));
    await openDraft(page, complexName);
    observe("complex_ui_cannot_edit", await page.getByRole("button", { name: "提交真实结构编辑", exact: true }).isDisabled());
    status = "PASS";
  } finally {
    const report = { status, phase, startedAtUtc, completedAtUtc: new Date().toISOString(), checks,
      sourceHead: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(), scope: context.apiOnly ? "API_ONLY: real OIDC/API/PG/Jena exact edit and assessment" : context.uiOnly ? "UI_ONLY: real UI/API exact editing and persistence" : "real M2 UI/API/PG/Jena/RustFS with retained G2 chain", notRun: [...(context.apiOnly || context.uiOnly ? [...(context.apiOnly ? ["UI editing/layout/keyboard"] : []), "publication/formal query/rollback", "compatibility and other six runtime gates"] : []), "real LLM", "full OWL reasoning", "Windows/Intel native", "production HA/SLO"] };
    await writeFile(resolve(evidence, context.apiOnly ? "m2-api.json" : context.uiOnly ? "m2-ui.json" : "m2-browser.json"), JSON.stringify(report, null, 2) + "\n");
    if (status !== "PASS" || checks.length === 0) process.exitCode = 1;
  }
}
