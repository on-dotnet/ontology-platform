import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { axiomFixture, elementDetailFixture, elementFixture, ontologyFixture } from '@/test/fixtures';
import { captureDownloads, mockApi, renderApp, type RouteHandler } from '@/test/utils';

import { displayEdges, layoutGraph } from './graph-layout';

const moltenSteel = elementFixture({ synonyms: [{ lang: 'zh', text: '铁水' }] });
const ladle = elementFixture({ id: 'el-ladle', localName: 'Ladle', labelZh: '钢包', labelEn: 'Ladle', definitionZh: '盛装钢水的容器。' });
const holds = elementFixture({
  id: 'el-holds',
  kind: 'relation_type',
  localName: 'holds',
  labelZh: '盛装',
  labelEn: 'holds',
  definitionZh: null,
  domainId: 'el-ladle',
  rangeId: 'el-molten-steel',
});
const temperature = elementFixture({
  id: 'el-temperature',
  kind: 'property',
  localName: 'temperature',
  labelZh: '温度',
  labelEn: 'Temperature',
  definitionZh: '钢水的温度。',
  domainId: 'el-molten-steel',
  datatype: 'decimal',
  unit: '℃',
  required: true,
});
const shape = elementFixture({
  id: 'el-shape',
  kind: 'constraint',
  localName: 'MoltenSteelShape',
  iri: 'https://example.org/ontology/steel#MoltenSteelShape',
  labelZh: '钢水校验',
  labelEn: null,
  definitionZh: null,
  domainId: 'el-molten-steel',
  rules: [
    {
      pathId: 'el-temperature',
      minCount: 1,
      maxCount: null,
      minInclusive: { iri: null, lexical: '1580', datatype: 'decimal', lang: null },
      allowedValuesLost: false,
      message: [{ lang: 'zh', text: '钢水温度不得低于 1580℃' }],
    },
  ],
  origin: 'import',
});
const disjoint = axiomFixture({ flags: ['non_standard'] });
// Imported: only an English name, the inverse of `holds`, no domain or range.
const heldBy = elementFixture({
  id: 'el-held-by',
  kind: 'relation_type',
  localName: 'heldBy',
  iri: 'urn:metals:heldBy',
  explicitIri: true,
  labelZh: null,
  labelEn: 'held by',
  definitionZh: null,
  inverseId: 'el-holds',
  origin: 'import',
});
// Imported without any name: shown by its local name.
const slab = elementFixture({ id: 'el-slab', localName: 'Slab', iri: 'urn:metals:Slab', explicitIri: true, labelZh: null, labelEn: null, definitionZh: null, origin: 'import' });
const all = [moltenSteel, ladle, holds, temperature, shape, disjoint, heldBy, slab];

function ontologyServer(extra: Record<string, RouteHandler> = {}) {
  return mockApi({
    'GET /api/ontologies': () => [ontologyFixture()],
    'GET /api/ontologies/:id/elements': ({ query }) => {
      const kind = query.get('kind');
      const q = query.get('q');
      return all.filter(
        (element) =>
          (!kind || element.kind === kind) &&
          (!q || (element.labelZh ?? '').includes(q) || element.synonyms.some((synonym) => synonym.text.includes(q))),
      );
    },
    'GET /api/ontologies/:id/elements/:elementId': ({ params }) => {
      const element = all.find((item) => item.id === params.elementId) ?? moltenSteel;
      return elementDetailFixture(element, [
        {
          changeSetId: 'cs-converter',
          changeSetTitle: '识别：转炉炼钢工艺规程.docx',
          itemId: 'item-1',
          op: 'create',
          mergedAt: '2026-11-21T08:00:00Z',
          evidence: [{ id: 'ev-1', documentId: 'doc-converter', chunkId: 'chunk-1', quote: '钢水温度不得低于 1580℃', charStart: 2, charEnd: 15 }],
        },
      ]);
    },
    'GET /api/ontologies/:id/graph': () => ({
      nodes: [
        { id: 'el-molten-steel', label: '钢水', localName: 'MoltenSteel', parentId: null, propertyCount: 1 },
        { id: 'el-ladle', label: '钢包', localName: 'Ladle', parentId: null, propertyCount: 0 },
        { id: 'el-steel-ladle', label: '精炼钢包', localName: 'RefiningLadle', parentId: 'el-ladle', propertyCount: 0 },
      ],
      edges: [
        { id: 'edge-holds', source: 'el-ladle', target: 'el-molten-steel', kind: 'relation', label: '盛装' },
        { id: 'edge-sub', source: 'el-steel-ladle', target: 'el-ladle', kind: 'subclass', label: null },
      ],
    }),
    ...extra,
  });
}

describe('ontology list view', () => {
  it('filters by kind and searches by name or synonym', async () => {
    const user = userEvent.setup();
    const api = ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    expect(within(table).getAllByRole('row')).toHaveLength(all.length + 1);

    await user.click(screen.getByRole('radio', { name: '属性' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).getByRole('button', { name: '温度' })).toBeInTheDocument();
    expect(api.requests.some((request) => request.path.endsWith('/elements') && request.query.get('kind') === 'property')).toBe(true);
    expect(screen.getByRole('list', { name: '当前筛选条件' })).toHaveTextContent('类型：属性');

    await user.click(screen.getByRole('button', { name: '移除筛选条件“类型：属性”' }));
    await user.type(screen.getByRole('searchbox', { name: '搜索名称或同义词' }), '铁水');
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).getByRole('button', { name: '钢水' })).toBeInTheDocument();
    const searched = api.requests.filter((request) => request.query.get('q') === '铁水');
    expect(searched.length).toBeGreaterThan(0);
    expect(searched.every((request) => request.query.get('kind') === null)).toBe(true);
  });

  it('opens an element in the side panel with definition, synonyms, structure and provenance', async () => {
    const user = userEvent.setup();
    ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(within(table).getByRole('button', { name: '钢水' }));

    const sheet = await screen.findByRole('dialog', { name: '钢水' });
    expect(within(sheet).getByText('转炉冶炼得到的液态钢。')).toBeInTheDocument();
    expect(within(sheet).getByText('铁水')).toBeInTheDocument();
    expect(within(sheet).getByText('属性（1）')).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: '温度' })).toBeInTheDocument();
    expect(within(sheet).getByText('关系（1）')).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: '盛装' })).toBeInTheDocument();
    expect(within(sheet).getByRole('link', { name: '识别：转炉炼钢工艺规程.docx' })).toHaveAttribute('href', '/review/cs-converter');
    expect(within(sheet).getByText('钢水温度不得低于 1580℃')).toBeInTheDocument();

    // Related elements open in the same panel.
    await user.click(within(sheet).getByRole('button', { name: '温度' }));
    expect(await screen.findByRole('dialog', { name: '温度' })).toHaveTextContent('℃');
  });

  it('names elements without a Chinese name by their English or local name, and shows the inverse of a relation', async () => {
    const user = userEvent.setup();
    ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    expect(within(table).getByRole('button', { name: 'Slab' })).toBeInTheDocument();
    await user.click(within(table).getByRole('button', { name: 'held by' }));

    const sheet = await screen.findByRole('dialog', { name: 'held by' });
    expect(within(sheet).getByText('urn:metals:heldBy')).toBeInTheDocument();
    const inverse = within(sheet).getByText('互逆关系').nextElementSibling as HTMLElement;
    expect(within(inverse).getByRole('button', { name: '盛装' })).toBeInTheDocument();
  });
});

describe('constraints and axioms', () => {
  it('lists axioms by their Turtle and opens the full fragment with its subject and rewrite warning', async () => {
    const user = userEvent.setup();
    const api = ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(screen.getByRole('radio', { name: '高级公理' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(api.requests.some((request) => request.path.endsWith('/elements') && request.query.get('kind') === 'axiom')).toBe(true);
    expect(within(table).getByText('所属：钢水')).toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: 'steel:MoltenSteel owl:disjointWith steel:Slag .' }));
    const sheet = await screen.findByRole('dialog', { name: '高级公理' });
    expect(sheet.querySelector('pre')).toHaveTextContent('steel:MoltenSteel owl:disjointWith steel:Slag .');
    expect(within(sheet).getByRole('button', { name: '非标准写法' })).toHaveAccessibleDescription('在 Protégé 中打开时会改写这条公理。');

    // The subject opens in the same panel and lists the axiom among its related axioms.
    await user.click(within(sheet).getByRole('button', { name: '钢水' }));
    const subject = await screen.findByRole('dialog', { name: '钢水' });
    expect(within(subject).getByRole('button', { name: 'steel:MoltenSteel owl:disjointWith steel:Slag .' })).toBeInTheDocument();
  });

  it('shows a constraint with its target type, IRI and rule table', async () => {
    const user = userEvent.setup();
    ontologyServer();
    renderApp('/ontology?ontology=onto-steel&view=list');

    const table = await screen.findByRole('table', { name: '本体元素' });
    await user.click(screen.getByRole('radio', { name: '约束' }));
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).getByText('目标类型：钢水')).toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: '钢水校验' }));
    const sheet = await screen.findByRole('dialog', { name: '钢水校验' });
    expect(within(sheet).getByText('https://example.org/ontology/steel#MoltenSteelShape')).toBeInTheDocument();
    const rules = within(sheet).getByRole('table', { name: '约束规则' });
    const [, row] = within(rules).getAllByRole('row');
    expect(row).toHaveTextContent('温度');
    expect(row).toHaveTextContent('至少 1 个');
    expect(row).toHaveTextContent('≥ 1580');
    expect(row).toHaveTextContent('钢水温度不得低于 1580℃');
    expect(within(sheet).getByRole('button', { name: '钢水' })).toBeInTheDocument();
  });
});

describe('graph layout', () => {
  it('draws subclass edges from parent to child so parents rank above children', () => {
    const graph = {
      nodes: [
        { id: 'parent', label: '钢包', localName: 'Ladle', parentId: null, propertyCount: 0 },
        { id: 'child', label: '精炼钢包', localName: 'RefiningLadle', parentId: 'parent', propertyCount: 0 },
      ],
      edges: [{ id: 'sub', source: 'child', target: 'parent', kind: 'subclass' as const, label: null }],
    };
    expect(displayEdges(graph)).toEqual([{ id: 'sub', source: 'parent', target: 'child', kind: 'subclass', label: null }]);
    const { nodes } = layoutGraph(graph);
    const parent = nodes.find((node) => node.node.id === 'parent');
    const child = nodes.find((node) => node.node.id === 'child');
    expect(parent && child && parent.y < child.y).toBe(true);
  });
});

describe('ontology graph view', () => {
  // React Flow measures nodes with ResizeObserver and DOM geometry, which jsdom does not provide.
  const descriptors = {
    offsetWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth'),
    offsetHeight: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight'),
  };

  beforeAll(() => {
    Object.defineProperties(HTMLElement.prototype, {
      offsetWidth: {
        configurable: true,
        get(this: HTMLElement) {
          return Number.parseFloat(this.style.width) || 1;
        },
      },
      offsetHeight: {
        configurable: true,
        get(this: HTMLElement) {
          return Number.parseFloat(this.style.height) || 1;
        },
      },
    });
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      configurable: true,
      value: () => ({ x: 0, y: 0, width: 40, height: 14 }),
    });
  });

  afterAll(() => {
    if (descriptors.offsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', descriptors.offsetWidth);
    if (descriptors.offsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', descriptors.offsetHeight);
  });

  beforeEach(() => {
    class MeasuringResizeObserver {
      private readonly callback: ResizeObserverCallback;
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
      }
      observe(target: Element) {
        this.callback([{ target } as ResizeObserverEntry], this);
      }
      unobserve() {}
      disconnect() {}
    }
    class DOMMatrixStub {
      m22: number;
      constructor(transform?: string) {
        const scale = /scale\(([\d.]+)\)/.exec(transform ?? '')?.[1];
        this.m22 = scale ? Number(scale) : 1;
      }
    }
    vi.stubGlobal('ResizeObserver', MeasuringResizeObserver);
    vi.stubGlobal('DOMMatrixReadOnly', DOMMatrixStub);
  });

  it('renders one node per object type and one edge per relation or parent link', async () => {
    ontologyServer();
    const { container } = renderApp('/ontology?ontology=onto-steel');

    expect(await screen.findByRole('figure', { name: '本体图谱：3 个对象类型，2 条连线' })).toBeInTheDocument();
    await waitFor(() => expect(container.ownerDocument.querySelectorAll('.react-flow__node')).toHaveLength(3));
    await waitFor(() => expect(container.ownerDocument.querySelectorAll('.react-flow__edge')).toHaveLength(2));
    expect(screen.getByText('精炼钢包')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '适应窗口' })).toBeInTheDocument();
  });

  it('switches to the list view and keeps it in the URL', async () => {
    const user = userEvent.setup();
    ontologyServer();
    const { router } = renderApp('/ontology?ontology=onto-steel');

    await screen.findByRole('figure');
    await user.click(screen.getByRole('radio', { name: '列表' }));
    expect(await screen.findByRole('table', { name: '本体元素' })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ ontology: 'onto-steel', view: 'list' });
  });

  it('exports the working version as a Turtle file', async () => {
    const user = userEvent.setup();
    const downloads = captureDownloads();
    const api = ontologyServer({
      'GET /api/ontologies/:id/export': () =>
        new Response('@prefix owl: <http://www.w3.org/2002/07/owl#> .\n', { headers: { 'Content-Type': 'text/turtle' } }),
    });
    renderApp('/ontology?ontology=onto-steel');

    await user.click(await screen.findByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByRole('menuitem', { name: '导出 Turtle' }));

    await waitFor(() => expect(downloads.names).toEqual(['steel.ttl']));
    expect(api.calls('GET', '/api/ontologies/onto-steel/export')[0]?.query.get('format')).toBe('turtle');
    expect(downloads.created).toHaveBeenCalledTimes(1);
    expect((await screen.findAllByText('已导出 Turtle 文件')).length).toBeGreaterThan(0);
  });
});
