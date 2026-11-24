import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from '@codemirror/language';
import { turtle } from '@codemirror/legacy-modes/mode/turtle';
import { Annotation, Compartment, EditorState, type Extension } from '@codemirror/state';
import { drawSelection, EditorView, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from '@codemirror/view';
import { tags } from '@lezer/highlight';
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';

import { cn } from '@/lib/cn';

export interface TurtleEditorHandle {
  /** Puts the cursor at the start of a 1-based line, scrolls it into view and focuses the editor. */
  revealLine: (line: number) => void;
  focus: () => void;
}

export interface TurtleEditorProps {
  value: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  /** Shown, selectable and navigable with the keyboard, but not editable. */
  readOnly?: boolean;
  'aria-label'?: string;
  'aria-labelledby'?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
  'aria-required'?: boolean;
  /** Size of the editor box, e.g. a height; the text scrolls inside it. */
  className?: string;
  ref?: Ref<TurtleEditorHandle>;
}

// The legacy mode styles any word starting with a capital as a comment, so class names such as
// `ex:MoltenSteel` would look commented out; only `#` starts a comment in Turtle.
const turtleParser: typeof turtle = {
  ...turtle,
  token: (stream, state) => {
    const style = turtle.token(stream, state);
    return style === 'comment' && stream.string.charAt(stream.start) !== '#' ? 'keyword' : style;
  },
};

const turtleLanguage = StreamLanguage.define(turtleParser);

// Colors are design tokens, so both themes follow the app's light and dark palettes.
const highlightStyle = HighlightStyle.define([
  { tag: tags.comment, color: 'var(--muted-foreground)', fontStyle: 'italic' },
  { tag: tags.string, color: 'var(--success-strong)' },
  { tag: tags.atom, color: 'var(--primary-strong)' },
  { tag: tags.meta, color: 'var(--info-strong)', fontWeight: '600' },
  { tag: tags.special(tags.variableName), color: 'var(--secondary-strong)' },
  { tag: tags.keyword, color: 'var(--foreground)' },
  { tag: tags.operator, color: 'var(--muted-foreground)' },
]);

const editorTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'var(--card)', color: 'var(--foreground)', fontSize: '0.8125rem' },
  // The wrapper draws the focus ring.
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'inherit', lineHeight: '1.6', overflow: 'auto' },
  '.cm-content': { caretColor: 'var(--foreground)', padding: '8px 0' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--foreground)' },
  '.cm-gutters': { backgroundColor: 'var(--muted)', color: 'var(--muted-foreground)', borderRight: '1px solid var(--border)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--border)', color: 'var(--foreground)' },
  '.cm-activeLine': { backgroundColor: 'var(--muted)' },
  '.cm-selectionBackground, &.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-content ::selection': {
    backgroundColor: 'var(--primary-soft)',
  },
});

/** Marks transactions that load a new value from the props, which are not the user's edits. */
const external = Annotation.define<boolean>();

type AriaProps = Pick<TurtleEditorProps, 'aria-label' | 'aria-labelledby' | 'aria-describedby' | 'aria-invalid' | 'aria-required'>;

function contentAttributes(aria: AriaProps, readOnly: boolean): Extension {
  const attributes: Record<string, string> = { 'aria-readonly': String(readOnly) };
  for (const [name, value] of Object.entries(aria)) {
    if (value !== undefined && value !== false) attributes[name] = String(value);
  }
  return EditorView.contentAttributes.of(attributes);
}

/**
 * Turtle source editor (CodeMirror 6 with the legacy Turtle mode): line numbers, syntax colors in
 * design tokens, undo history. Tab is left to move focus on, as the keyboard expects outside editors.
 */
export default function TurtleEditorView({ value, onChange, onBlur, readOnly = false, className, ref, ...aria }: TurtleEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const [compartments] = useState(() => ({ readOnly: new Compartment(), attributes: new Compartment() }));
  // The latest props, for CodeMirror's listeners and for creating the editor, without recreating it.
  const latest = useRef({ value, onChange, onBlur, readOnly, aria });
  useEffect(() => {
    latest.current = { value, onChange, onBlur, readOnly, aria };
  });

  const { 'aria-label': label, 'aria-labelledby': labelledBy, 'aria-describedby': describedBy } = aria;
  const { 'aria-invalid': invalid, 'aria-required': required } = aria;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const initial = latest.current;
    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: initial.value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          drawSelection(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          EditorView.lineWrapping,
          turtleLanguage,
          syntaxHighlighting(highlightStyle),
          editorTheme,
          compartments.readOnly.of(EditorState.readOnly.of(initial.readOnly)),
          compartments.attributes.of(contentAttributes(initial.aria, initial.readOnly)),
          EditorView.updateListener.of((update) => {
            if (update.docChanged && !update.transactions.some((transaction) => transaction.annotation(external))) {
              latest.current.onChange?.(update.state.doc.toString());
            }
            if (update.focusChanged && !update.view.hasFocus) latest.current.onBlur?.();
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [compartments]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== value) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value }, annotations: external.of(true) });
    }
  }, [value]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: [
        compartments.readOnly.reconfigure(EditorState.readOnly.of(readOnly)),
        compartments.attributes.reconfigure(
          contentAttributes(
            { 'aria-label': label, 'aria-labelledby': labelledBy, 'aria-describedby': describedBy, 'aria-invalid': invalid, 'aria-required': required },
            readOnly,
          ),
        ),
      ],
    });
  }, [compartments, readOnly, label, labelledBy, describedBy, invalid, required]);

  useImperativeHandle(
    ref,
    () => ({
      revealLine: (line: number) => {
        const view = viewRef.current;
        if (!view) return;
        const { doc } = view.state;
        const position = doc.line(Math.min(Math.max(Math.trunc(line), 1), doc.lines)).from;
        view.dispatch({ selection: { anchor: position }, effects: EditorView.scrollIntoView(position, { y: 'center' }) });
        view.focus();
      },
      focus: () => viewRef.current?.focus(),
    }),
    [],
  );

  return (
    <div
      ref={hostRef}
      className={cn(
        'overflow-hidden rounded-lg border border-border font-mono',
        'focus-within:outline-2 focus-within:outline-offset-1 focus-within:outline-ring',
        invalid && 'border-error',
        className,
      )}
    />
  );
}
