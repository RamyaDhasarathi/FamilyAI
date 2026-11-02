// Shell for secondary pages (Settings, placeholders, 404): black with the
// onboarding glow and dust, a glass back button, the title, and a centred
// scrolling column (max 720 px on wide screens).
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { ChevronLeft } from 'lucide-react';
import clsx from 'clsx';
import { T } from '../theme/typography';
import { webCopy } from '../mocks/webData';
import { useEscape } from '../hooks/useEscape';
import { useHotkeys } from '../hooks/useHotkeys';
import { OnboardingBackdrop } from './OnboardingBackdrop';
import { Pressable } from './Pressable';
import { ToastHost } from './Toast';
import { goBack } from './navigation';

export function BackButton({ onClick, label = webCopy.back }: { onClick: () => void; label?: string }) {
  return (
    <Pressable className="round-btn" onClick={onClick} aria-label={label}>
      <ChevronLeft size={20} aria-hidden />
    </Pressable>
  );
}

export function ScreenShell({ title, children, back = '/', wide, actions }: { title: string; children: ReactNode; back?: string; wide?: boolean; actions?: ReactNode }) {
  const navigate = useNavigate();
  const onBack = () => goBack(navigate, back);
  useEscape(true, onBack);
  useHotkeys({ Backspace: onBack });
  return (
    <div className="shell">
      <OnboardingBackdrop />
      <header className={clsx('shell__bar', wide && 'shell__bar--wide')}>
        <BackButton onClick={onBack} />
        <h1 className={clsx(T.sheetTitle, 'shell__title')}>{title}</h1>
        {actions ? <div className="shell__actions">{actions}</div> : null}
      </header>
      <main id="main" className={clsx('shell__body', wide && 'shell__body--wide')}>
        {children}
      </main>
      <ToastHost bottom={24} />
    </div>
  );
}
