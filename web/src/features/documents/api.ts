import { queryOptions, useInfiniteQuery, useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type DocumentInfo = components['schemas']['DocumentInfo'];
export type DocumentStatus = DocumentInfo['status'];
export type DocumentPage = components['schemas']['DocumentList'];
export type Chunk = components['schemas']['ChunkInfo'];

/** First page size of the documents table (backend maximum is 100). */
export const DOCUMENTS_PAGE_SIZE = 50;
/** Documents in progress are polled every 3 seconds. */
export const DOCUMENTS_POLL_MS = 3_000;

const PROCESSING: readonly DocumentStatus[] = ['queued', 'parsing', 'extracting'];

export function isProcessing(document: Pick<DocumentInfo, 'status'>): boolean {
  return PROCESSING.includes(document.status);
}

export const documentKeys = {
  all: ['documents'] as const,
  list: (ontologyId: string) => [...documentKeys.all, 'list', ontologyId] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
  chunk: (id: string, chunkId: string) => [...documentKeys.all, 'detail', id, 'chunk', chunkId] as const,
};

/** Paged documents of an ontology; polls while any loaded document is still being processed. */
export function useDocuments(ontologyId: string) {
  return useInfiniteQuery({
    queryKey: documentKeys.list(ontologyId),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/documents', {
          params: { query: { ontologyId, limit: DOCUMENTS_PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some(isProcessing)) ? DOCUMENTS_POLL_MS : false,
  });
}

export function documentQueryOptions(id: string) {
  return queryOptions({
    queryKey: documentKeys.detail(id),
    queryFn: () => unwrap(api.GET('/api/documents/{id}', { params: { path: { id } } })),
    staleTime: 60_000,
  });
}

/** One document's metadata, e.g. to name the source of a change set or a piece of evidence. */
export function useDocument(id: string | null | undefined) {
  return useQuery({ ...documentQueryOptions(id ?? ''), enabled: Boolean(id) });
}

export function useChunk(documentId: string, chunkId: string) {
  return useQuery({
    queryKey: documentKeys.chunk(documentId, chunkId),
    queryFn: () => unwrap(api.GET('/api/documents/{id}/chunks/{chunkId}', { params: { path: { id: documentId, chunkId } } })),
    // Chunk text never changes once parsed.
    staleTime: Infinity,
  });
}

export function uploadDocument(ontologyId: string, file: File): Promise<DocumentInfo> {
  return unwrap(
    api.POST('/api/documents', {
      // The generated type models the binary part as a string; the serializer sends the File itself.
      body: { ontologyId, file: file as unknown as string },
      bodySerializer: (body) => {
        const form = new FormData();
        form.append('ontologyId', body.ontologyId);
        form.append('file', file, file.name);
        return form;
      },
    }),
  );
}

export function retryDocument(id: string): Promise<DocumentInfo> {
  return unwrap(api.POST('/api/documents/{id}/retry', { params: { path: { id } } }));
}
