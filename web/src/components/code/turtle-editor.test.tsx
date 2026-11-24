import { EditorView } from '@codemirror/view';
import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TurtleEditor } from './turtle-editor';
import TurtleEditorView, { type TurtleEditorHandle } from './turtle-editor-view';

const TEXT = ['@prefix owl: <http://www.w3.org/2002/07/owl#> .', '@prefix ex: <https://example.org/steel#> .', '', 'ex:Ladle a owl:Class .', ''].join('\n');

function viewOf(box: HTMLElement): EditorView {
  const view = EditorView.findFromDOM(box);
  if (!view) throw new Error('No editor');
  return view;
}

describe('Turtle editor', () => {
  it('shows the text in a labelled text box that is read-only until editing is allowed', () => {
    const { rerender } = render(<TurtleEditorView value={TEXT} readOnly aria-label="工作版本的 Turtle" />);
    const box = screen.getByRole('textbox', { name: '工作版本的 Turtle' });
    expect(box).toHaveAttribute('aria-readonly', 'true');
    expect(box).toHaveTextContent('ex:Ladle a owl:Class .');
    expect(viewOf(box).state.readOnly).toBe(true);

    rerender(<TurtleEditorView value={TEXT} aria-label="工作版本的 Turtle" aria-invalid aria-describedby="turtle-error" />);
    expect(box).toHaveAttribute('aria-readonly', 'false');
    expect(box).toHaveAttribute('aria-invalid', 'true');
    expect(box).toHaveAttribute('aria-describedby', 'turtle-error');
    expect(viewOf(box).state.readOnly).toBe(false);
  });

  it('reports the user’s edits, but not a new value from its props', () => {
    const onChange = vi.fn();
    const { rerender } = render(<TurtleEditorView value={TEXT} onChange={onChange} aria-label="片段" />);
    const view = viewOf(screen.getByRole('textbox', { name: '片段' }));

    view.dispatch({ changes: { from: view.state.doc.length, insert: 'ex:Slab a owl:Class .\n' } });
    expect(onChange).toHaveBeenLastCalledWith(`${TEXT}ex:Slab a owl:Class .\n`);

    onChange.mockClear();
    rerender(<TurtleEditorView value="ex:Heat a owl:Class ." onChange={onChange} aria-label="片段" />);
    expect(view.state.doc.toString()).toBe('ex:Heat a owl:Class .');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('moves the cursor to the start of a line on request', () => {
    const ref = createRef<TurtleEditorHandle>();
    render(<TurtleEditorView ref={ref} value={TEXT} aria-label="片段" />);
    const view = viewOf(screen.getByRole('textbox', { name: '片段' }));

    ref.current?.revealLine(4);
    expect(view.state.selection.main.head).toBe(view.state.doc.line(4).from);
    // Lines past the end go to the last line.
    ref.current?.revealLine(99);
    expect(view.state.selection.main.head).toBe(view.state.doc.line(view.state.doc.lines).from);
  });

  it('loads on first use behind a placeholder of the same size', async () => {
    render(<TurtleEditor value={TEXT} readOnly aria-label="工作版本的 Turtle" className="h-80" />);
    expect(await screen.findByRole('textbox', { name: '工作版本的 Turtle' })).toHaveTextContent('ex:Ladle a owl:Class .');
  });
});
