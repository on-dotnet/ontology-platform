import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CloudUpload } from 'lucide-react';
import { useRef, useState, type DragEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { useToast } from '@/components/feedback/toast';
import { Button } from '@/components/ui/button';
import { CreateOntologyDialog } from '@/features/ontologies/create-ontology-dialog';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

import { documentKeys, uploadDocument } from './api';
import { ACCEPT_ATTRIBUTE, MAX_UPLOAD_MB, validateFiles } from './upload-rules';

export interface UploadProblem {
  fileName: string;
  message: string;
}

interface UploadOptions {
  /** Ontology to upload into; undefined while unknown or when none exists yet. */
  ontologyId: string | undefined;
  /** True once the ontologies are loaded and there are none: the user names one first. */
  needsOntology: boolean;
  /** Called after at least one file was accepted by the server. */
  onUploaded?: (ontologyId: string) => void;
}

/**
 * Validates files (type, size), creates the first ontology when there is none, then uploads
 * the files one by one. Render `dialog` once; show `problems` near the upload control.
 */
export function useDocumentUpload({ ontologyId, needsOntology, onUploaded }: UploadOptions) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  // Files chosen before an ontology exists wait here until the user names one.
  const [waiting, setWaiting] = useState<File[] | null>(null);
  const [problems, setProblems] = useState<UploadProblem[]>([]);

  const mutation = useMutation({
    mutationFn: async ({ target, files }: { target: string; files: File[] }) => {
      const failed: UploadProblem[] = [];
      let uploaded = 0;
      for (const file of files) {
        try {
          await uploadDocument(target, file);
          uploaded += 1;
        } catch (error) {
          failed.push({ fileName: file.name, message: message(error) });
        }
      }
      return { target, uploaded, failed };
    },
    onSuccess: async ({ target, uploaded, failed }) => {
      if (failed.length > 0) setProblems((current) => [...current, ...failed]);
      if (uploaded === 0) return;
      toast.success(t('upload.uploaded', { count: uploaded }), t('upload.uploadedDescription'));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: documentKeys.list(target) }),
        queryClient.invalidateQueries({ queryKey: ['workbench'] }),
      ]);
      onUploaded?.(target);
    },
  });

  const submit = (files: readonly File[]) => {
    const { accepted, rejected } = validateFiles(files);
    setProblems(
      rejected.map(({ fileName, reason }) => ({
        fileName,
        message: t(`upload.rejected.${reason}`, { size: MAX_UPLOAD_MB }),
      })),
    );
    if (accepted.length === 0) return;
    if (ontologyId) mutation.mutate({ target: ontologyId, files: accepted });
    else if (needsOntology) setWaiting(accepted);
  };

  const dialog = (
    <CreateOntologyDialog
      open={waiting !== null}
      onOpenChange={(open) => {
        if (!open) setWaiting(null);
      }}
      onCreated={(ontology) => {
        const files = waiting ?? [];
        setWaiting(null);
        if (files.length > 0) mutation.mutate({ target: ontology.id, files });
      }}
    />
  );

  return {
    submit,
    dialog,
    problems,
    dismissProblems: () => setProblems([]),
    isUploading: mutation.isPending,
  };
}

/** A hidden file input opened by a visible button. */
export function useFilePicker(onFiles: (files: File[]) => void) {
  const { t } = useTranslation();
  const ref = useRef<HTMLInputElement>(null);
  const input = (
    <input
      ref={ref}
      type="file"
      multiple
      accept={ACCEPT_ATTRIBUTE}
      tabIndex={-1}
      className="sr-only"
      aria-label={t('upload.fileInputLabel')}
      onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        // Allow choosing the same file again after a rejection.
        event.target.value = '';
        if (files.length > 0) onFiles(files);
      }}
    />
  );
  return { open: () => ref.current?.click(), input };
}

/** Drag-and-drop handlers for an element that accepts files. */
export function useFileDrop(onFiles: (files: File[]) => void, enabled = true) {
  const [dragging, setDragging] = useState(false);
  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes('Files');
  const handlers = enabled
    ? {
        onDragEnter: (event: DragEvent) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          setDragging(true);
        },
        onDragOver: (event: DragEvent) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
        },
        onDragLeave: (event: DragEvent) => {
          // Ignore moves between child elements.
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDragging(false);
        },
        onDrop: (event: DragEvent) => {
          event.preventDefault();
          setDragging(false);
          const files = Array.from(event.dataTransfer?.files ?? []);
          if (files.length > 0) onFiles(files);
        },
      }
    : {};
  return { dragging, handlers };
}

interface UploadDropZoneProps {
  onFiles: (files: File[]) => void;
  busy?: boolean;
  /** Text above the button; defaults to "drag documents here". */
  title?: ReactNode;
  /** Use the primary button style when this is the main action of its area. */
  primary?: boolean;
  className?: string;
}

/** Dashed drop target with a "choose files" button and the accepted formats. */
export function UploadDropZone({ onFiles, busy = false, title, primary = false, className }: UploadDropZoneProps) {
  const { t } = useTranslation();
  const picker = useFilePicker(onFiles);
  const { dragging, handlers } = useFileDrop(onFiles, !busy);
  return (
    <div
      {...handlers}
      data-dragging={dragging || undefined}
      className={cn(
        'flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border bg-card/60 px-6 py-8 text-center transition-colors',
        'data-[dragging]:border-primary data-[dragging]:bg-primary-soft',
        className,
      )}
    >
      <span className="flex size-12 items-center justify-center rounded-xl bg-primary-soft text-primary-strong">
        <CloudUpload className="size-6" aria-hidden />
      </span>
      <p className="text-sm font-medium text-foreground">{title ?? t('upload.dropTitle')}</p>
      {picker.input}
      <Button variant={primary ? 'primary' : 'secondary'} onClick={picker.open} loading={busy}>
        {busy ? t('upload.uploading') : t('upload.chooseFiles')}
      </Button>
      <p className="text-xs text-muted-foreground">{t('upload.hint', { size: MAX_UPLOAD_MB })}</p>
    </div>
  );
}

/** Red banner listing the files that were not uploaded and why. */
export function UploadProblems({ problems, onDismiss, className }: { problems: readonly UploadProblem[]; onDismiss: () => void; className?: string }) {
  const { t } = useTranslation();
  if (problems.length === 0) return null;
  return (
    <InlineNotice
      tone="error"
      title={t('upload.problemsTitle', { count: problems.length })}
      className={className}
      action={
        <Button variant="secondary" size="sm" onClick={onDismiss}>
          {t('common.dismiss')}
        </Button>
      }
    >
      <ul className="space-y-0.5">
        {problems.map((problem, index) => (
          <li key={`${problem.fileName}-${index}`}>
            <span className="font-medium">{problem.fileName}</span>
            {t('common.colon')}
            {problem.message}
          </li>
        ))}
      </ul>
    </InlineNotice>
  );
}
