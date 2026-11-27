import type { EditItem, Element } from '@/features/ontologies/api';

import { canBeKey, columnFits, type CatalogTable, type Join, type TableBinding, type TypeBindingView } from './api';

type BoundTable = NonNullable<TypeBindingView['table']>;
type Target = Pick<BoundTable, 'elementId' | 'revision'>;
type DependentKind = 'property_binding' | 'relation_binding';

interface RelationSlot {
  key: string;
  subject: Element;
  isDomain: boolean;
  otherId: string | null;
  other: BoundTable | null;
  current: (Target & { join: Join }) | null;
}

function relationSlots(typeId: string, all: readonly Element[], view: TypeBindingView, views: TypeBindingView[], bindings: Element[]) {
  const slots = new Map<string, RelationSlot>();
  const byId = new Map(all.map((element) => [element.id, element]));
  const tablesByType = new Map(views.map((entry) => [entry.typeId, entry.table]));
  const typesByTable = new Map(views.map((entry) => [entry.table?.elementId, entry.typeId]));
  const tableId = view.table?.elementId;
  const add = (subjectId: string, isDomain: boolean, otherId: string | null, current: RelationSlot['current']) => {
    const subject = byId.get(subjectId);
    if (!subject || subject.status !== 'active') return;
    const domain = isDomain ? typeId : otherId;
    const range = isDomain ? otherId : typeId;
    const key = JSON.stringify([subjectId, domain, range]);
    if (slots.has(key) && !current) return;
    slots.set(key, { key, subject, isDomain: domain === typeId, otherId, other: tablesByType.get(otherId ?? '') ?? null, current });
  };
  for (const relation of all) {
    if (relation.kind !== 'relation_type') continue;
    // As in the server's view, a relation without its other endpoint has nothing to join to.
    if (relation.domainId === typeId && relation.rangeId) add(relation.id, true, relation.rangeId, null);
    if (relation.rangeId === typeId && relation.domainId) add(relation.id, false, relation.domainId, null);
  }
  // A relation can bind several pairs of subtypes. The view names its declared endpoint,
  // while the binding element records the actual endpoint chosen for this join.
  const actualIds = new Set<string>();
  for (const element of bindings) {
    if (!tableId || !element.subjectId || element.binding?.target !== 'join') continue;
    const isDomain = element.domainId === tableId;
    if (!isDomain && element.rangeId !== tableId) continue;
    const otherTable = isDomain ? element.rangeId : element.domainId;
    const otherId = otherTable === tableId ? typeId : typesByTable.get(otherTable ?? '');
    if (!otherId) continue;
    add(element.subjectId, isDomain, otherId, { elementId: element.id, revision: element.revision, join: element.binding.join });
    actualIds.add(element.id);
  }
  for (const relation of view.relations) {
    const current = relation.join && !actualIds.has(relation.join.elementId) ? relation.join : null;
    add(relation.relationId, relation.direction === 'out', relation.otherTypeId, current);
  }
  return [...slots.values()];
}

export function bindingModel(
  type: Element, all: readonly Element[], view: TypeBindingView, views: TypeBindingView[],
  propertyBindings: Element[], relationBindings: Element[],
) {
  const byId = new Map(all.map((element) => [element.id, element]));
  const ancestors = new Set<string>();
  let ancestor: Element | undefined = type;
  while (ancestor && !ancestors.has(ancestor.id)) {
    ancestors.add(ancestor.id);
    ancestor = ancestor.parentId ? byId.get(ancestor.parentId) : undefined;
  }
  const dependents = new Map<string, Target & { kind: DependentKind }>();
  const columns = new Map<string, Target & { column: string }>();
  for (const { propertyId, column } of view.properties) {
    if (column) {
      columns.set(propertyId, column);
      dependents.set(column.elementId, { ...column, kind: 'property_binding' });
    }
  }
  for (const { join } of view.relations) {
    if (join) dependents.set(join.elementId, { ...join, kind: 'relation_binding' });
  }
  if (view.table) {
    const tableId = view.table.elementId;
    for (const element of propertyBindings) {
      if (element.parentId !== tableId || !element.subjectId || element.binding?.target !== 'column') continue;
      const target = { elementId: element.id, revision: element.revision };
      dependents.set(element.id, { ...target, kind: 'property_binding' });
      columns.set(element.subjectId, { ...target, column: element.binding.column });
    }
    for (const element of relationBindings) {
      if (element.domainId === tableId || element.rangeId === tableId) {
        dependents.set(element.id, { kind: 'relation_binding', elementId: element.id, revision: element.revision });
      }
    }
  }
  const properties = all.filter((item) =>
    item.kind === 'property' && item.status === 'active' && (!item.domainId || ancestors.has(item.domainId)),
  ).map((subject) => ({ subject, current: columns.get(subject.id) }));
  return {
    typeId: type.id, original: view.table, properties, dependents,
    relations: relationSlots(type.id, all, view, views, relationBindings),
  };
}

export type BindingModel = ReturnType<typeof bindingModel>;

export function replacementChanged(before: BindingModel, after: BindingModel, items: EditItem[]) {
  if (before.original?.elementId !== after.original?.elementId || before.original?.revision !== after.original?.revision) return true;
  if (before.dependents.size !== after.dependents.size) return true;
  for (const { elementId, revision } of before.dependents.values()) {
    if (after.dependents.get(elementId)?.revision !== revision) return true;
  }
  // Link-table columns refer to the other endpoint's keys by position.
  const peers = new Set<string | null | undefined>();
  for (const { fields } of items) {
    if (fields?.binding?.target === 'join' && fields.binding.join.kind === 'link_table') {
      peers.add(fields.domainRef);
      peers.add(fields.rangeRef);
    }
  }
  const latest = new Map(after.relations.map((slot) => [slot.key, slot.other]));
  return before.relations.some((slot) => {
    if (!slot.other || !peers.has(slot.other.elementId)) return false;
    const other = latest.get(slot.key);
    return !other || other.elementId !== slot.other.elementId || !sameColumns(other.keyColumns, slot.other.keyColumns);
  });
}

export interface Choices {
  keys: string[];
  columns: Record<string, string>;
  joins: Record<string, Join | null>;
}

/** Link columns match endpoint keys by position. A different key needs a new mapping. */
function resetLinkColumns(join: Extract<Join, { kind: 'link_table' }>, slot: RelationSlot, typeId: string): Join {
  const self = slot.otherId === typeId;
  return {
    ...join,
    sourceColumns: slot.isDomain || self ? [] : join.sourceColumns,
    targetColumns: !slot.isDomain || self ? [] : join.targetColumns,
  };
}

export function withKeys(model: BindingModel, choices: Choices, keys: string[]): Choices {
  const joins = { ...choices.joins };
  for (const slot of model.relations) {
    const join = joins[slot.key];
    if (join?.kind === 'link_table') joins[slot.key] = resetLinkColumns(join, slot, model.typeId);
  }
  return { ...choices, keys, joins };
}

function sameTable(original: BoundTable | null, dataSourceId: string, table: CatalogTable) {
  return original?.dataSource.id === dataSourceId && original.schema === table.schema && original.table === table.name;
}

export function defaultChoices(model: BindingModel, dataSourceId: string, table: CatalogTable): Choices {
  const same = sameTable(model.original, dataSourceId, table);
  const primary = table.primaryKey ?? [];
  // A usable subset of a composite primary key need not identify a row.
  const usablePrimary = primary.every((key) => table.columns.some((column) => column.name === key && canBeKey(column)));
  const keys = same && model.original ? model.original.keyColumns : usablePrimary ? primary : [];
  const columns: Choices['columns'] = {};
  for (const { subject, current } of model.properties) {
    if (current && (same || table.columns.some((col) => col.name === current.column && columnFits(subject.datatype, col)))) {
      columns[subject.id] = current.column;
    }
  }
  const joins: Choices['joins'] = {};
  for (const slot of model.relations) {
    const join = slot.current?.join;
    if (!join || model.original?.dataSource.id !== dataSourceId) continue;
    if (!same && join.kind === 'link_table' && !sameColumns(model.original.keyColumns, keys)) {
      joins[slot.key] = resetLinkColumns(join, slot, model.typeId);
      continue;
    }
    if (!same && join.kind === 'foreign_key') {
      const self = slot.otherId === model.typeId;
      const holder = (join.side === 'source') === slot.isDomain;
      const required = self ? [...join.columns, ...join.references] : holder ? join.columns : join.references;
      if (!required.every((key) => table.columns.some((column) => column.name === key))) continue;
    }
    joins[slot.key] = join;
  }
  return { keys, columns, joins };
}

export function joinProblem(join: Join, sourceKeys: number, targetKeys: number) {
  if (join.kind === 'link_table' && (!join.schema || !join.table)) return 'tableRequired';
  const [left, right] = join.kind === 'foreign_key' ? [join.columns, join.references] : [join.sourceColumns, join.targetColumns];
  if (!left.length || !right.length) return 'joinColumnsRequired';
  if (left.length > 8 || right.length > 8) return 'joinTooMany';
  if (join.kind === 'foreign_key' && left.length !== right.length) return 'columnsMismatch';
  if (join.kind === 'link_table' && (left.length !== sourceKeys || right.length !== targetKeys)) return 'linkColumnsMismatch';
  return undefined;
}

function remove(kind: DependentKind | 'type_binding', { elementId, revision }: Target): EditItem {
  return { op: 'delete', kind, targetElementId: elementId, targetRevision: revision };
}

export function unbindEdits(model: BindingModel): EditItem[] {
  if (!model.original) return [];
  return [
    ...[...model.dependents.values()].map((target) => remove(target.kind, target)),
    remove('type_binding', model.original),
  ];
}

function sameColumns(left: string[], right: string[]) {
  return left.length === right.length && left.every((column, index) => column === right[index]);
}

function sameJoin(left: Join, right: Join) {
  if (left.kind === 'foreign_key' && right.kind === 'foreign_key') {
    return left.side === right.side && sameColumns(left.columns, right.columns) && sameColumns(left.references, right.references);
  }
  return left.kind === 'link_table' && right.kind === 'link_table' && left.schema === right.schema && left.table === right.table
    && sameColumns(left.sourceColumns, right.sourceColumns) && sameColumns(left.targetColumns, right.targetColumns);
}

export function bindingEdits(model: BindingModel, dataSourceId: string, table: CatalogTable, choices: Choices): EditItem[] {
  const { original } = model;
  const same = sameTable(original, dataSourceId, table);
  const items: EditItem[] = [];
  if (original && !same) {
    items.push(...unbindEdits(model));
  }
  const binding: TableBinding = { target: 'table', dataSourceId, schema: table.schema, table: table.name, keyColumns: choices.keys };
  let ownRef: string;
  if (original && same) {
    ownRef = original.elementId;
    if (!sameColumns(choices.keys, original.keyColumns)) {
      items.push({ op: 'update', kind: 'type_binding', targetElementId: ownRef, targetRevision: original.revision, fields: { binding } });
    }
  } else {
    // A bare UUID denotes an existing element. getRandomValues also works on the HTTP development host.
    ownRef = `new:table:${crypto.getRandomValues(new Uint32Array(4)).join('-')}`;
    items.push({ op: 'create', kind: 'type_binding', tempRef: ownRef, fields: { subjectRef: model.typeId, binding } });
  }
  for (const { subject, current } of model.properties) {
    const old = same ? current : undefined;
    const column = choices.columns[subject.id] ?? '';
    if (column === (old?.column ?? '')) continue;
    const binding = { target: 'column', column } as const;
    if (old) {
      items.push(column
        ? { op: 'update', kind: 'property_binding', targetElementId: old.elementId, targetRevision: old.revision, fields: { binding } }
        : remove('property_binding', old));
    } else {
      items.push({ op: 'create', kind: 'property_binding', fields: { subjectRef: subject.id, parentRef: ownRef, binding } });
    }
  }
  for (const slot of model.relations) {
    const old = same ? slot.current : null;
    const join = choices.joins[slot.key];
    if (!join) {
      if (old) items.push(remove('relation_binding', old));
      continue;
    }
    const binding = { target: 'join', join } as const;
    if (old) {
      if (!sameJoin(old.join, join)) {
        items.push({ op: 'update', kind: 'relation_binding', targetElementId: old.elementId, targetRevision: old.revision, fields: { binding } });
      }
      continue;
    }
    const otherRef = slot.otherId === model.typeId ? ownRef : slot.other?.elementId;
    if (!otherRef) continue;
    items.push({
      op: 'create', kind: 'relation_binding',
      fields: { subjectRef: slot.subject.id, domainRef: slot.isDomain ? ownRef : otherRef, rangeRef: slot.isDomain ? otherRef : ownRef, binding },
    });
  }
  return items;
}
