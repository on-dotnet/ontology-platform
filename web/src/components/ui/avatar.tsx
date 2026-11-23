import { Avatar as BaseAvatar } from '@base-ui/react/avatar';

import { cn } from '@/lib/cn';

/** First character of a CJK name, or up to two initials of a multi-word Latin name. */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  const words = trimmed.split(/\s+/);
  if (words.length > 1 && /^[a-z]/i.test(trimmed)) {
    return words
      .slice(0, 2)
      .map((word) => word.charAt(0))
      .join('')
      .toUpperCase();
  }
  return Array.from(trimmed)[0]?.toUpperCase() ?? '?';
}

export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <BaseAvatar.Root
      className={cn(
        'inline-flex size-9 shrink-0 select-none items-center justify-center overflow-hidden rounded-full',
        'bg-primary-soft text-sm font-semibold text-primary-strong',
        className,
      )}
    >
      <BaseAvatar.Fallback>{initials(name)}</BaseAvatar.Fallback>
    </BaseAvatar.Root>
  );
}
