// 404 in the design language (AGENT_WEB.md §8.8).
import { Link } from 'react-router';
import clsx from 'clsx';
import { pageMeta, webCopy } from '../../mocks/webData';
import { T } from '../../theme/typography';
import { usePageMeta } from '../../hooks/usePageMeta';
import { MiniGem } from '../../components/MiniGem';
import { OnboardingBackdrop } from '../../components/OnboardingBackdrop';

export default function NotFound() {
  usePageMeta(pageMeta.notFound);
  return (
    <div className="shell">
      <OnboardingBackdrop />
      <main id="main" className="not-found page-in">
        <MiniGem size={140} still />
        <h1 className={T.greeting}>{webCopy.notFound.title}</h1>
        <p className={clsx(T.small)}>{webCopy.notFound.body}</p>
        <Link to="/" className="pill pill--primary">
          {webCopy.notFound.home}
        </Link>
      </main>
    </div>
  );
}
