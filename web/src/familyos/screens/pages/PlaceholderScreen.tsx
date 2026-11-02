// Profile-menu destinations without a real page yet (AGENT_WEB.md §8.5),
// in the new design language. "Help and feedback" also lists the keyboard
// shortcuts (§9).
import { useParams } from 'react-router';
import clsx from 'clsx';
import { copy } from '../../mocks/data';
import { pageMeta, webCopy } from '../../mocks/webData';
import { T } from '../../theme/typography';
import { usePageMeta } from '../../hooks/usePageMeta';
import { MiniGem } from '../../components/MiniGem';
import { ScreenShell } from '../../components/ScreenShell';
import { ShortcutList } from '../panels/HelpOverlay';
import { slug } from '../panels/menuSlug';
import NotFound from './NotFound';

const TITLES = [...copy.profileMenu.rows, copy.profileMenu.help];

export default function PlaceholderScreen() {
  const { slug: s } = useParams();
  const title = TITLES.find((t) => slug(t) === s);
  usePageMeta(pageMeta.placeholder(title ?? ''));
  if (!title) return <NotFound />;
  const help = title === copy.profileMenu.help;
  return (
    <ScreenShell title={title}>
      <div className="placeholder-card card">
        <MiniGem size={120} still />
        <p className={T.small}>{copy.placeholder(title)}</p>
      </div>
      {help ? (
        <section className="placeholder-help card" aria-labelledby="sc-title">
          <h2 id="sc-title" className={clsx(T.section, 'section-label')} style={{ marginTop: 14 }}>
            {webCopy.help.title}
          </h2>
          <ShortcutList />
        </section>
      ) : null}
    </ScreenShell>
  );
}
