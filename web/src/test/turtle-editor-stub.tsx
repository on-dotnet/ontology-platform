import { useImperativeHandle, useRef } from 'react';

import type { TurtleEditorProps } from '@/components/code/turtle-editor';

/**
 * Stand-in for the CodeMirror editor in page tests (jsdom cannot type into it): a text area with
 * the same props and handle. Install with
 * `vi.mock('@/components/code/turtle-editor', () => import('@/test/turtle-editor-stub'))`.
 */
export function TurtleEditor({ value, onChange, onBlur, readOnly, className, ref, ...aria }: TurtleEditorProps) {
  const area = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(
    ref,
    () => ({
      revealLine: (line: number) => {
        const element = area.current;
        if (!element) return;
        const offset = element.value
          .split('\n')
          .slice(0, Math.max(line - 1, 0))
          .reduce((sum, text) => sum + text.length + 1, 0);
        element.focus();
        element.setSelectionRange(offset, offset);
      },
      focus: () => area.current?.focus(),
    }),
    [],
  );
  return (
    <textarea
      ref={area}
      className={className}
      value={value}
      readOnly={readOnly}
      onChange={(event) => onChange?.(event.target.value)}
      onBlur={onBlur}
      {...aria}
    />
  );
}
