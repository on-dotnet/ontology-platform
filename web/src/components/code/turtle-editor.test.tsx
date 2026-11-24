import { undo } from '@codemirror/commands';
import { EditorView } from '@codemirror/view';
import { render, screen, waitFor } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

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

  it('is named by the label it points to', () => {
    render(
      <>
        <span id="fragment-label">Turtle 片段</span>
        <TurtleEditorView value="" aria-labelledby="fragment-label" aria-required />
      </>,
    );
    const box = screen.getByRole('textbox', { name: 'Turtle 片段' });
    expect(box).toHaveClass('cm-content');
    expect(box).toHaveAttribute('contenteditable', 'true');
    expect(box).toHaveAttribute('aria-required', 'true');
  });

  it('keeps Esc to itself, so a dialog around it stays open', () => {
    const onOpenChange = vi.fn();
    render(
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>新建高级公理</DialogTitle>
          <TurtleEditorView value="ex:Ladle a owl:Class ." aria-label="片段" />
          <button type="button">其他</button>
        </DialogContent>
      </Dialog>,
    );
    const escape = () => new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    screen.getByRole('textbox', { name: '片段' }).dispatchEvent(escape());
    expect(onOpenChange).not.toHaveBeenCalled();

    // Elsewhere in the dialog, Esc closes it as usual.
    screen.getByRole('button', { name: '其他' }).dispatchEvent(escape());
    expect(onOpenChange).toHaveBeenCalledWith(false, expect.anything());
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

  it('does not offer a new value from its props to undo', () => {
    const { rerender } = render(<TurtleEditorView value={TEXT} aria-label="片段" />);
    const view = viewOf(screen.getByRole('textbox', { name: '片段' }));
    rerender(<TurtleEditorView value="ex:Heat a owl:Class ." aria-label="片段" />);
    expect(undo(view)).toBe(false);
    expect(view.state.doc.toString()).toBe('ex:Heat a owl:Class .');
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

  it('loads on first use behind a placeholder of the same size, then takes requests through its handle', async () => {
    const ref = createRef<TurtleEditorHandle>();
    const { container } = render(<TurtleEditor ref={ref} value={TEXT} readOnly aria-label="工作版本的 Turtle" className="h-80" />);
    const placeholder = container.querySelector('.animate-pulse');
    expect(placeholder).toHaveClass('h-80');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();

    const box = await screen.findByRole('textbox', { name: '工作版本的 Turtle' });
    expect(box).toHaveTextContent('ex:Ladle a owl:Class .');
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
    expect(box.closest('.h-80')).not.toBeNull();

    await waitFor(() => expect(ref.current).not.toBeNull());
    ref.current?.revealLine(4);
    const view = viewOf(box);
    expect(view.state.selection.main.head).toBe(view.state.doc.line(4).from);
  });
});
