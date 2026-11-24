import { lazy, Suspense } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/cn';

import type { TurtleEditorProps } from './turtle-editor-view';

export type { TurtleEditorHandle, TurtleEditorProps } from './turtle-editor-view';

// CodeMirror is only needed in expert mode; it loads with the first editor shown.
const TurtleEditorView = lazy(() => import('./turtle-editor-view'));

/** Turtle source editor; see `TurtleEditorView`. A skeleton of the same size shows while it loads. */
export function TurtleEditor(props: TurtleEditorProps) {
  return (
    <Suspense fallback={<Skeleton className={cn('rounded-lg', props.className)} />}>
      <TurtleEditorView {...props} />
    </Suspense>
  );
}
