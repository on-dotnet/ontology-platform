import { beforeEach, describe, expect, it, vi } from "vitest";
import { isValidElement, type ComponentProps, type ReactElement, type ReactNode } from "react";
import type { OntologyDraft, SaveDraftRequest } from "../../lib/api/g2-generated";
import type { PlatformIdentity } from "../../lib/api/generated";

/** Node环境仅提供hook调度；不替换被测TSX的事件处理器或缓冲更新逻辑。 */
const hooks = vi.hoisted(() => {
  type Cleanup = void | (() => void);
  type Effect = { kind: "effect"; dependencies?: readonly unknown[]; cleanup: Cleanup };
  const active: Host[] = [];
  class Host {
    slots: unknown[] = [];
    cursor = 0;
    effects: Array<() => void> = [];

    render<T>(component: () => T): T {
      active.push(this);
      this.cursor = 0;
      this.effects = [];
      let result: T;
      try { result = component(); } finally { active.pop(); }
      this.effects.forEach(effect => effect());
      return result;
    }

    unmount() {
      for (const slot of this.slots) {
        const effect = slot as Partial<Effect> | undefined;
        if (effect?.kind === "effect" && typeof effect.cleanup === "function") effect.cleanup();
      }
    }
  }
  function useState<T>(initial: T | (() => T)): [T, (next: T | ((current: T) => T)) => void] {
    const host = active.at(-1)!;
    const index = host.cursor++;
    if (!(index in host.slots)) host.slots[index] = typeof initial === "function" ? (initial as () => T)() : initial;
    return [host.slots[index] as T, next => {
      host.slots[index] = typeof next === "function" ? (next as (current: T) => T)(host.slots[index] as T) : next;
    }];
  }
  function useRef<T>(initial: T) {
    const host = active.at(-1)!;
    const index = host.cursor++;
    if (!(index in host.slots)) host.slots[index] = { current: initial };
    return host.slots[index] as { current: T };
  }
  function useEffect(setup: () => Cleanup, dependencies?: readonly unknown[]) {
    const host = active.at(-1)!;
    const index = host.cursor++;
    const previous = host.slots[index] as Effect | undefined;
    if (previous && dependencies && previous.dependencies?.length === dependencies.length
      && dependencies.every((dependency, offset) => Object.is(dependency, previous.dependencies![offset]))) return;
    const next: Effect = { kind: "effect", dependencies, cleanup: undefined };
    host.slots[index] = next;
    host.effects.push(() => {
      if (typeof previous?.cleanup === "function") previous.cleanup();
      next.cleanup = setup();
    });
  }
  return { Host, useState, useRef, useEffect };
});
const api = vi.hoisted(() => ({ drafts: vi.fn(), draft: vi.fn(), supportProfile: vi.fn(), saveDraft: vi.fn() }));
vi.mock("react", async importOriginal => ({
  ...await importOriginal<typeof import("react")>(),
  useState: hooks.useState, useRef: hooks.useRef, useEffect: hooks.useEffect,
  useCallback: <T extends (...arguments_: never[]) => unknown>(callback: T) => callback,
}));
vi.mock("../../lib/api/g2-client", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/api/g2-client")>(),
  createG2Client: () => api,
}));

import { OntologyWorkspace } from "./workspace";
import { SourceEditor } from "./source-editor";

type Element = ReactElement<Record<string, unknown>>;
const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: null, dataHash: "d", bundleHash: "b" };
const draft: OntologyDraft = {
  draftId: "draft-a", assetId: "asset-a", name: "资产甲", revision: 1, etag: '"1"',
  scope: { organizationId: "org", siteIds: ["site"] }, baseReleaseId: null,
  sources: { ontologyTurtle: "# ontology original\r\n", shapesTurtle: "# shapes original\r\n", vocabularyTurtle: null, dataTurtle: "# data original\r\n" },
  hashes, ownerSubjectId: "operator", updatedAtUtc: "2026-10-27T00:00:00Z",
  projection: { revision: 1, hashes, triples: [], nodes: [], edges: [], structuralEditAllowed: true, diagnostics: [] },
};
const other = { ...draft, draftId: "draft-b", assetId: "asset-b", name: "资产乙" };
const initialIdentity: PlatformIdentity = { subjectId: "operator", displayName: "操作员", roles: ["platform.operator"], scopes: [] };

function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function event(element: Element, name: string, value?: unknown): unknown {
  return (element.props[name] as (event: unknown) => unknown)(value);
}
async function settle() { for (let index = 0; index < 8; index++) await Promise.resolve(); }
function delayed() {
  let resolve!: (bytes: ArrayBuffer) => void;
  let reject!: (cause: Error) => void;
  const promise = new Promise<ArrayBuffer>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve: (value: string) => resolve(new TextEncoder().encode(value).buffer), reject };
}

/** 初始目录读取来自IO替身；测试断言只针对实际工作区/编辑器事件之后的用户缓冲。 */
async function workspace() {
  const host = new hooks.Host();
  const editorHost = new hooks.Host();
  let identity = initialIdentity;
  const render = () => host.render(() => OntologyWorkspace({ identity }));
  const sourceProps = () => elements(render()).find(element => element.type === SourceEditor)!.props as ComponentProps<typeof SourceEditor>;
  const editor = () => editorHost.render(() => SourceEditor(sourceProps()));
  function input(label: string) {
    return elements(render()).find(element => element.type === "input" && element.props["aria-label"] === label)!;
  }
  function click(label: string) {
    const button = elements(render()).find(element => element.type === "button" && text(element) === label)!;
    event(button, "onClick");
  }
  async function open(name: string) {
    const button = elements(render()).find(element => element.type === "button" && text(element).startsWith(name))!;
    event(button, "onClick");
    await settle();
  }
  function field(value: keyof OntologyDraft["sources"]) {
    const selector = elements(editor()).find(element => element.type === "select")!;
    event(selector, "onChange", { target: { value } });
  }
  function typeSource(value: string) {
    const area = elements(editor()).find(element => element.type === "textarea")!;
    event(area, "onChange", { target: { value } });
  }
  function upload(read = delayed(), size = 32) {
    const fileInput = elements(editor()).find(element => element.type === "input" && element.props.type === "file")!;
    const target = { value: "selected.ttl", files: [{ size, arrayBuffer: () => read.promise }] };
    const done = event(fileInput, "onChange", { currentTarget: target }) as Promise<void>;
    return { ...read, done };
  }
  render();
  await settle();
  await open("资产甲");
  return {
    render, sourceProps, upload, field, typeSource, click, open,
    name: () => input("资产名称").props.value,
    rename: (value: string) => event(input("资产名称"), "onChange", { target: { value } }),
    reason: (value: string) => event(input("变更理由"), "onChange", { target: { value } }),
    changeIdentity: () => { identity = { ...identity, subjectId: "next-operator" }; render(); },
    errors: () => elements(editor()).filter(element => element.props.role === "alert").map(text),
    unmount: () => host.unmount(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.drafts.mockResolvedValue([draft, other]);
  api.draft.mockImplementation((id: string) => Promise.resolve(id === other.draftId ? other : draft));
  api.supportProfile.mockResolvedValue({ profileId: "p", version: "1", hash: "h", reasoningMode: "ASSERTED_ONLY", capabilities: [] });
  api.saveDraft.mockImplementation((_id: string, body: SaveDraftRequest) => Promise.resolve({ ...draft, name: body.name, sources: body.sources, revision: 2 }));
  vi.stubGlobal("window", new EventTarget());
  vi.stubGlobal("document", new EventTarget());
});

describe("实际TSX延迟文件导入不能覆盖后发用户操作", () => {
  it("延迟期间修改名称和另一个源，完成时只合并导入源", async () => {
    const view = await workspace();
    const pending = view.upload();
    view.rename("等待期间新名称");
    view.field("dataTurtle");
    view.typeSource("# newer data\n");
    pending.resolve("\uFEFF# imported 🏭\r\n");
    await pending.done;
    expect(view.name()).toBe("等待期间新名称");
    expect(view.sourceProps().sources.dataTurtle).toBe("# newer data\n");
    expect(view.sourceProps().sources.ontologyTurtle).toBe("\uFEFF# imported 🏭\r\n");
  });
  it("同源新键入使先前文件读取失效", async () => {
    const view = await workspace();
    const pending = view.upload();
    view.typeSource("# newer typing\n");
    pending.resolve("# old file\n");
    await pending.done;
    expect(view.sourceProps().sources.ontologyTurtle).toBe("# newer typing\n");
  });
  it("同源两个导入乱序完成，最后发起的文件获胜", async () => {
    const view = await workspace();
    const first = view.upload();
    const second = view.upload();
    second.resolve("# second file\n");
    await second.done;
    first.resolve("# first file\n");
    await first.done;
    expect(view.sourceProps().sources.ontologyTurtle).toBe("# second file\n");
  });
  it("不同源乱序完成保留两个导入，不恢复旧整份缓冲", async () => {
    const view = await workspace();
    const ontology = view.upload();
    view.field("dataTurtle");
    const data = view.upload();
    data.resolve("# imported data\n");
    await data.done;
    ontology.resolve("# imported ontology\n");
    await ontology.done;
    expect(view.sourceProps().sources.dataTurtle).toBe("# imported data\n");
    expect(view.sourceProps().sources.ontologyTurtle).toBe("# imported ontology\n");
  });
  it("切换草稿后旧读取不能恢复前一个草稿", async () => {
    const view = await workspace();
    const pending = view.upload();
    await view.open("资产乙");
    pending.resolve("# old draft file\n");
    await pending.done;
    expect(view.name()).toBe("资产乙");
    expect(view.sourceProps().sources).toEqual(other.sources);
  });
  it("同草稿保存成新修订后拒绝旧revision读取", async () => {
    const view = await workspace();
    view.rename("revision2名称");
    view.reason("延迟期间保存");
    const pending = view.upload();
    view.click("保存新修订");
    await settle();
    pending.resolve("# revision1 old file\n");
    await pending.done;
    expect(text(view.render())).toContain("revision 2");
    expect(view.name()).toBe("revision2名称");
    expect(view.sourceProps().sources).toEqual(draft.sources);
  });
  it("显式丢弃后旧读取不能重新制造dirty", async () => {
    const view = await workspace();
    view.rename("待丢弃名称");
    const pending = view.upload();
    view.click("丢弃未保存修改");
    pending.resolve("# discarded file\n");
    await pending.done;
    expect(view.name()).toBe("资产甲");
    expect(view.sourceProps().sources).toEqual(draft.sources);
  });
  it("切换到新建缓冲后旧草稿读取不能进入新资产", async () => {
    const view = await workspace();
    const pending = view.upload();
    view.click("新建 / 导入资产");
    view.rename("新建资产");
    pending.resolve("# old draft file\n");
    await pending.done;
    expect(view.name()).toBe("新建资产");
    expect(view.sourceProps().sources.ontologyTurtle).toBe("");
  });
  it("新建缓冲发起导入后打开草稿，旧结果不能留在隐藏新建缓冲", async () => {
    const view = await workspace();
    view.click("新建 / 导入资产");
    const pending = view.upload();
    await view.open("资产乙");
    pending.resolve("# obsolete new asset file\n");
    await pending.done;
    view.click("新建 / 导入资产");
    expect(view.sourceProps().sources.ontologyTurtle).toBe("");
  });
  it("会话身份改变后旧读取不能提交", async () => {
    const view = await workspace();
    const pending = view.upload();
    view.changeIdentity();
    pending.resolve("# previous identity\n");
    await pending.done;
    expect(view.sourceProps().sources).toEqual(draft.sources);
  });
  it("后发超限导入也应使先前读取失效", async () => {
    const view = await workspace();
    const pending = view.upload();
    await view.upload(delayed(), 262145).done;
    pending.resolve("# earlier file\n");
    await pending.done;
    expect(view.sourceProps().sources).toEqual(draft.sources);
    expect(view.errors().join("")).toContain("超过256 KiB");
  });
  it("旧失败不得覆盖新成功导入的可见状态", async () => {
    const view = await workspace();
    const first = view.upload();
    const second = view.upload();
    second.resolve("# second file\n");
    await second.done;
    first.reject(new Error("old read failed"));
    await first.done;
    expect(view.sourceProps().sources.ontologyTurtle).toBe("# second file\n");
    expect(view.errors()).toEqual([]);
  });
  it("卸载后旧导入不得修改已存在的缓冲", async () => {
    const view = await workspace();
    const pending = view.upload();
    view.unmount();
    pending.resolve("# unmounted read\n");
    await pending.done;
    expect(view.sourceProps().sources).toEqual(draft.sources);
  });
});
