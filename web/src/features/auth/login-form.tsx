import { useMutation } from '@tanstack/react-query';
import { Eye, EyeOff } from 'lucide-react';
import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tooltip } from '@/components/ui/tooltip';
import { useErrorMessage } from '@/i18n/error-message';

import { login, type UserInfo } from './api';

interface LoginFormProps {
  onSuccess: (user: UserInfo) => void | Promise<void>;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const usernameId = useId();
  const passwordId = useId();
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState({ username: false, password: false });
  // A field the user never typed in stays quiet on blur (e.g. after clicking the language switch).
  const [dirty, setDirty] = useState({ username: false, password: false });
  const [submitted, setSubmitted] = useState(false);

  const mutation = useMutation({ mutationFn: login, onSuccess });

  const errors = {
    username: username.trim() ? undefined : t('login.usernameRequired'),
    password: password ? undefined : t('login.passwordRequired'),
  };
  const visibleErrors = {
    username: (touched.username && dirty.username) || submitted ? errors.username : undefined,
    password: (touched.password && dirty.password) || submitted ? errors.password : undefined,
  };
  const hasValidationErrors = Boolean(errors.username || errors.password);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    // Validation is summarized at the top; focus goes to the first invalid field (ui-guidelines §8).
    if (errors.username) {
      usernameRef.current?.focus();
      return;
    }
    if (errors.password) {
      passwordRef.current?.focus();
      return;
    }
    mutation.mutate({ username: username.trim(), password });
  };

  const toggleLabel = t(showPassword ? 'login.hidePassword' : 'login.showPassword');

  let notice: ReactNode = null;
  if (submitted && hasValidationErrors) {
    notice = <InlineNotice tone="error">{t('login.validationSummary')}</InlineNotice>;
  } else if (mutation.isError) {
    notice = (
      <InlineNotice tone="error" title={t('login.failedTitle')}>
        {message(mutation.error)}
      </InlineNotice>
    );
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-5">
      {notice}

      <div className="space-y-2">
        <Label htmlFor={usernameId} required>
          {t('login.username')}
        </Label>
        <Input
          ref={usernameRef}
          id={usernameId}
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          // eslint-disable-next-line jsx-a11y/no-autofocus -- the sign-in page has a single task
          autoFocus
          aria-required
          aria-invalid={visibleErrors.username ? true : undefined}
          aria-describedby={visibleErrors.username ? `${usernameId}-error` : undefined}
          value={username}
          onChange={(event) => {
            setUsername(event.target.value);
            setDirty((state) => ({ ...state, username: true }));
          }}
          onBlur={() => setTouched((state) => ({ ...state, username: true }))}
          className="h-11"
        />
        <FieldError id={`${usernameId}-error`}>{visibleErrors.username}</FieldError>
      </div>

      <div className="space-y-2">
        <Label htmlFor={passwordId} required>
          {t('login.password')}
        </Label>
        <div className="relative">
          <Input
            ref={passwordRef}
            id={passwordId}
            name="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            aria-required
            aria-invalid={visibleErrors.password ? true : undefined}
            aria-describedby={visibleErrors.password ? `${passwordId}-error` : undefined}
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setDirty((state) => ({ ...state, password: true }));
            }}
            onBlur={() => setTouched((state) => ({ ...state, password: true }))}
            className="h-11 pr-11"
          />
          <Tooltip content={toggleLabel}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={toggleLabel}
              aria-controls={passwordId}
              onClick={() => setShowPassword((value) => !value)}
              className="absolute right-1.5 top-1/2 -translate-y-1/2"
            >
              {showPassword ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
            </Button>
          </Tooltip>
        </div>
        <FieldError id={`${passwordId}-error`}>{visibleErrors.password}</FieldError>
      </div>

      <Button type="submit" size="lg" className="w-full" loading={mutation.isPending}>
        {mutation.isPending ? t('login.submitting') : t('login.submit')}
      </Button>
    </form>
  );
}

function FieldError({ id, children }: { id: string; children: ReactNode }) {
  if (!children) return null;
  return (
    <p id={id} className="text-xs font-medium text-error-strong">
      {children}
    </p>
  );
}
