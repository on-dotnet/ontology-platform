import { ChevronDown, ChevronRight, ListChecks } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { EmptyState } from '@/components/states/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Pagination } from '@/components/ui/pagination';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { PageState } from '@/lib/pagination';

import { ViolationTable } from './violation-table';

type Rule = components['schemas']['RuleResult'];

const checkLabels: Record<string, string> = {
  minCount: 'ontologyPage.form.rules.minCount', maxCount: 'ontologyPage.form.rules.maxCount',
  minInclusive: 'ontologyPage.form.rules.minValue', maxInclusive: 'ontologyPage.form.rules.maxValue',
  minExclusive: 'metrics.exclusiveMinimum', maxExclusive: 'metrics.exclusiveMaximum',
  minLength: 'ontologyPage.form.rules.minLength', maxLength: 'ontologyPage.form.rules.maxLength',
  allowedValues: 'ontologyPage.form.rules.allowedValues', pattern: 'ontologyPage.form.rules.pattern',
  datatype: 'review.fields.datatype', nodeKind: 'metrics.nodeKind', class: 'ontologyPage.form.rules.classRef',
  path: 'rules.columns.path',
};

function RuleRow({ rule, typeLabel, expanded, onToggle }: { rule: Rule; typeLabel: string; expanded: boolean; onToggle: () => void }) {
  const { t } = useTranslation();
  const samplesId = useId();
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <>
      <TableRow>
        <TableCell className="align-top">
          <p className="font-medium">{rule.message || rule.constraintLabel}</p>
          {rule.propertyLabel && <p className="text-xs text-muted-foreground">{rule.propertyLabel}</p>}
        </TableCell>
        <TableCell>
          {rule.violations > 0 ? (
            <Button variant="secondary" size="sm" aria-expanded={expanded} aria-controls={expanded ? samplesId : undefined}
              className="text-error-strong" onClick={onToggle}>
              <Chevron aria-hidden />{t('metrics.violationCount', { count: rule.violations })}
            </Button>
          ) : !rule.unchecked.length && (
            rule.checks.length ? <Badge tone="success">{t('cq.result.pass')}</Badge> : <Badge tone="warning">{t('metrics.unchecked')}</Badge>
          )}
          {rule.unchecked.length > 0 && <div className="space-y-1 py-1">
            <Badge tone="warning">{t('metrics.unchecked')}</Badge>
            <ul className="space-y-1">{rule.unchecked.map(({ check, reason }, index) => (
              <li key={`${check}-${reason}-${index}`}>
                {checkLabels[check] && <span className="mr-2 font-medium">{t(checkLabels[check])}</span>}
                {t(`metrics.reasons.${reason}`)}
              </li>
            ))}</ul>
          </div>}
        </TableCell>
      </TableRow>
      {expanded && rule.violations > 0 && <TableRow id={samplesId}><TableCell colSpan={2} className="bg-muted/50">
        <ViolationTable rule={rule} typeLabel={typeLabel} />
      </TableCell></TableRow>}
    </>
  );
}

interface RuleTableProps {
  results: Rule[];
  typeLabel: string;
  page: PageState;
  expanded: ReadonlySet<string>;
  onToggle: (key: string) => void;
}

export function RuleTable({ results, typeLabel, page, expanded, onToggle }: RuleTableProps) {
  const { t } = useTranslation();
  if (!results.length) return <EmptyState icon={ListChecks} headingLevel="h3" title={t('metrics.noConstraints')} />;
  // Several property shapes can share both a constraint and a path in the same release.
  const occurrences = new Map<string, number>();
  const rows = results.map((rule) => {
    const path = `${rule.constraintId}/${rule.propertyId ?? ''}`;
    const occurrence = occurrences.get(path) ?? 0;
    occurrences.set(path, occurrence + 1);
    return { rule, key: `${path}/${occurrence}` };
  });
  return (
    <>
      <Table aria-label={t('metrics.rules')}>
        <TableHeader><TableRow><TableHead>{t('metrics.constraint')}</TableHead><TableHead>{t('documents.columns.status')}</TableHead></TableRow></TableHeader>
        <TableBody>{rows.slice(page.start, page.end).map(({ key, rule }) => (
          <RuleRow key={key} rule={rule} typeLabel={typeLabel} expanded={expanded.has(key)} onToggle={() => onToggle(key)} />
        ))}</TableBody>
      </Table>
      <Pagination state={page} total={results.length} />
    </>
  );
}
