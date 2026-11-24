import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

/** What the page the user is on works with, so the assistant can take it as context. */
export interface AssistantSelection {
  /** The ontology the page shows, when the URL does not say (e.g. a change set's review page). */
  ontologyId?: string | undefined;
  /** The element selected on the page, if any. */
  elementId?: string | null | undefined;
}

interface SelectionStore {
  selection: AssistantSelection;
  setSelection: (selection: AssistantSelection) => void;
}

const EMPTY: AssistantSelection = {};
const SelectionContext = createContext<SelectionStore | null>(null);

/** Lets pages tell the assistant panel what they show; both live inside the app shell. */
export function AssistantSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<AssistantSelection>(EMPTY);
  const store = useMemo(() => ({ selection, setSelection }), [selection]);
  return <SelectionContext.Provider value={store}>{children}</SelectionContext.Provider>;
}

/** What the current page published; empty when it published nothing. */
export function useAssistantSelection(): AssistantSelection {
  return useContext(SelectionContext)?.selection ?? EMPTY;
}

/** Publishes the page's ontology and selected element while the page is shown. */
export function usePublishAssistantSelection({ ontologyId, elementId }: AssistantSelection): void {
  const setSelection = useContext(SelectionContext)?.setSelection;
  useEffect(() => {
    if (!setSelection) return undefined;
    setSelection({ ontologyId, elementId: elementId ?? null });
    return () => setSelection(EMPTY);
  }, [setSelection, ontologyId, elementId]);
}
