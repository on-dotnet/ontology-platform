import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { NativeSelect } from '@/components/ui/native-select';
import { cn } from '@/lib/cn';

import type { OntologySummary } from './api';

interface OntologySelectorProps {
  ontologies: readonly OntologySummary[];
  value: string;
  onValueChange: (id: string) => void;
  className?: string;
}

/** Switches the ontology a page works on; the choice lives in the URL (`?ontology=`). */
export function OntologySelector({ ontologies, value, onValueChange, className }: OntologySelectorProps) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <label htmlFor={id} className="shrink-0 text-sm font-medium text-muted-foreground">
        {t('ontologies.selectorLabel')}
      </label>
      <NativeSelect
        id={id}
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        containerClassName="w-56 max-w-full"
        className="h-9"
      >
        {ontologies.map((ontology) => (
          <option key={ontology.id} value={ontology.id}>
            {ontology.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
