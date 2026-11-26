import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { WarnTip } from '@/components/feedback/hint-tip';
import { QueryState } from '@/components/states/query-state';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';

import { tableName, useCatalogTable, type CatalogTable, type Join, type TableBindingView } from './api';
import { CatalogTablePicker } from './catalog-table-picker';

type ForeignKeyJoin = Extract<Join, { kind: 'foreign_key' }>;
type Side = ForeignKeyJoin['side'];
const MAX_COLUMNS = 8;

interface RelationJoinEditorProps {
  name: string;
  dataSourceId: string;
  own: CatalogTable;
  ownKeys: string[];
  other: Pick<TableBindingView, 'schema' | 'table' | 'keyColumns'>;
  isDomain: boolean;
  value: Join | null;
  onChange: (value: Join | null) => void;
  error?: string;
}

interface ColumnGroupProps {
  label: string;
  table: CatalogTable;
  selected: string[];
  endpointKeys?: string[];
  onChange: (columns: string[]) => void;
}

function ColumnGroup({ label, table, selected, onChange, endpointKeys }: ColumnGroupProps) {
  const { t } = useTranslation();
  const id = useId();
  const names = new Set(table.columns.map((column) => column.name));
  // A renamed column in a saved join must still be visible and removable.
  const options = [...new Set([...names, ...selected])];
  return (
    <fieldset className="min-w-0 space-y-1">
      <legend className="text-sm font-medium">
        {label} <span aria-hidden className="text-error-strong">*</span>
      </legend>
      {endpointKeys && <p className="font-mono text-xs text-muted-foreground">
        {t('bindings.form.endpointKeys', { keys: endpointKeys.join(t('common.listSeparator')) })}
      </p>}
      {options.length === 0 && <p className="text-sm text-muted-foreground">{t('bindings.form.noCompatibleColumn')}</p>}
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {options.map((column, index) => {
          const order = selected.indexOf(column);
          const checked = order !== -1;
          const orderId = checked && selected.length > 1 ? `${id}-order-${index}` : undefined;
          return (
            <div key={column} className="flex items-center gap-1">
              <label className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label={column}
                  aria-describedby={orderId}
                  className="size-4 accent-primary focus-visible:outline-ring"
                  checked={checked}
                  disabled={!checked && selected.length >= MAX_COLUMNS}
                  onChange={(event) => {
                    const next = event.target.checked ? [...selected, column] : selected.filter((name) => name !== column);
                    onChange(next);
                  }}
                />
                <span className="break-all font-mono">{column}</span>
                {orderId && <span id={orderId} className="rounded bg-muted px-1 text-xs tabular-nums">{order + 1}</span>}
              </label>
              {!names.has(column) && <WarnTip>{t('bindings.check.missing_column')}</WarnTip>}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

export function RelationJoinEditor({
  name, dataSourceId, own, ownKeys, other, isDomain, value, onChange, error,
}: RelationJoinEditorProps) {
  const { t } = useTranslation();
  const id = useId();
  const ownSide: Side = isDomain ? 'source' : 'target';
  const ownName = tableName(own.schema, own.name);
  const otherName = tableName(other.schema, other.table);
  const schema = value?.kind === 'foreign_key' ? other.schema : value?.schema;
  const table = value?.kind === 'foreign_key' ? other.table : value?.table;
  const isOwnTable = schema === own.schema && table === own.name;
  const catalog = useCatalogTable(isOwnTable ? undefined : dataSourceId, schema, table);

  // Only initialize on a user action. A later catalog response must preserve the draft.
  function startForeignKey(side: Side) {
    const ownHoldsKey = side === ownSide;
    const holder = ownHoldsKey || isOwnTable ? own : catalog.data;
    const refSchema = ownHoldsKey ? other.schema : own.schema;
    const refTable = ownHoldsKey ? other.table : own.name;
    const refKeys = ownHoldsKey ? other.keyColumns : ownKeys;
    const matches = holder?.foreignKeys.filter((fk) => fk.refSchema === refSchema && fk.refTable === refTable);
    const match = matches?.length === 1 ? matches[0] : undefined;
    if (match && match.columns.length <= MAX_COLUMNS) {
      onChange({ kind: 'foreign_key', side, columns: match.columns, references: match.refColumns });
    } else {
      onChange({ kind: 'foreign_key', side, columns: [], references: refKeys.length <= MAX_COLUMNS ? refKeys : [] });
    }
  }

  function renderColumns(details: CatalogTable) {
    if (!value) return null;
    if (value.kind === 'foreign_key') {
      const ownHoldsKey = value.side === ownSide;
      return (
        <>
          <ColumnGroup
            label={t('bindings.form.columns')}
            table={ownHoldsKey ? own : details}
            selected={value.columns}
            onChange={(columns) => onChange({ ...value, columns })}
          />
          <ColumnGroup
            label={t('bindings.form.references')}
            table={ownHoldsKey ? details : own}
            selected={value.references}
            onChange={(references) => onChange({ ...value, references })}
          />
        </>
      );
    }
    return (
      <>
        <ColumnGroup
          label={t('bindings.form.sourceColumns')}
          endpointKeys={isDomain ? ownKeys : other.keyColumns}
          table={details}
          selected={value.sourceColumns}
          onChange={(sourceColumns) => onChange({ ...value, sourceColumns })}
        />
        <ColumnGroup
          label={t('bindings.form.targetColumns')}
          endpointKeys={isDomain ? other.keyColumns : ownKeys}
          table={details}
          selected={value.targetColumns}
          onChange={(targetColumns) => onChange({ ...value, targetColumns })}
        />
      </>
    );
  }

  return (
    <fieldset
      className="min-w-0 space-y-3 rounded-lg border border-border p-3"
      aria-invalid={error ? true : undefined}
      aria-describedby={error ? `${id}-error` : undefined}
    >
      <legend className="px-1 text-sm font-semibold">{name}</legend>
      <div className="space-y-1">
        <Label htmlFor={`${id}-kind`}>{t('bindings.form.joinKind')}</Label>
        <NativeSelect
          id={`${id}-kind`}
          value={value?.kind ?? 'none'}
          onChange={(event) => {
            switch (event.target.value) {
              case 'none':
                onChange(null);
                break;
              case 'foreign_key':
                startForeignKey(ownSide);
                break;
              case 'link_table':
                onChange({ kind: 'link_table', schema: '', table: '', sourceColumns: [], targetColumns: [] });
                break;
            }
          }}
        >
          <option value="none">{t('bindings.form.joinKinds.none')}</option>
          <option value="foreign_key">{t('bindings.form.joinKinds.foreign_key')}</option>
          <option value="link_table">{t('bindings.form.joinKinds.link_table')}</option>
        </NativeSelect>
      </div>
      {value?.kind === 'foreign_key' && (
        <div className="space-y-1">
          <Label htmlFor={`${id}-side`} required>{t('bindings.form.side')}</Label>
          <NativeSelect
            id={`${id}-side`}
            value={value.side}
            onChange={(event) => startForeignKey(event.target.value === 'source' ? 'source' : 'target')}
          >
            <option value="source">{t('bindings.form.sides.source', { table: isDomain ? ownName : otherName })}</option>
            <option value="target">{t('bindings.form.sides.target', { table: isDomain ? otherName : ownName })}</option>
          </NativeSelect>
        </div>
      )}
      {value?.kind === 'link_table' && (
        <CatalogTablePicker
          key={dataSourceId}
          dataSourceId={dataSourceId}
          label={t('bindings.form.linkTable')}
          value={value.schema && value.table ? { schema: value.schema, name: value.table } : null}
          onChange={(next) => {
            if (next.schema !== value.schema || next.name !== value.table) {
              onChange({ kind: 'link_table', schema: next.schema, table: next.name, sourceColumns: [], targetColumns: [] });
            }
          }}
        />
      )}
      {schema && table && (isOwnTable ? renderColumns(own) : (
        <QueryState query={catalog} requiredRole="editor">{renderColumns}</QueryState>
      ))}
      {error && <p id={`${id}-error`} className="text-sm text-error-strong">{error}</p>}
    </fieldset>
  );
}
