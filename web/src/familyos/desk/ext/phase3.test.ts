// MASTER_AGENT.md §7 Phase 3, §11 "every action writes an audit row": who
// handles a notice and a school's portal live in the one desk store and each
// change appends one audit row; no-ops write nothing.
import { beforeEach, describe, expect, it } from 'vitest';
import { buildDeskData } from '../data';
import { zoned } from '../format';
import { deskClock, useDesk } from '../store';
import { addPortal, assignNotice, handlerOf, normalizeUrl, schoolPages } from './phase3';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const st = () => useDesk.getState();
const notice = (id: string) => st().notices.find((n) => n.id === id)!;

beforeEach(() => {
  deskClock.now = () => NOW;
  useDesk.setState({ ...buildDeskData(NOW, TZ), actor: 'm_michael' });
});

describe('who handles a notice', () => {
  it('starts from the seed, changes with one audit row, and can be cleared', () => {
    expect(handlerOf(notice('n_recital'))).toBe('m_sarah');
    expect(handlerOf(notice('n_tripform'))).toBeNull();
    const n = st().audit.length;
    expect(assignNotice('n_tripform', 'm_sarah')).toBe(true);
    expect(handlerOf(notice('n_tripform'))).toBe('m_sarah');
    expect(st().audit).toHaveLength(n + 1);
    expect(st().audit.at(-1)).toMatchObject({ code: 'notice.assigned', actor: 'm_michael', sentence: 'Michael asked Sarah to handle “Field trip permission form”' });
    expect(assignNotice('n_tripform', 'm_sarah')).toBe(false);
    expect(st().audit).toHaveLength(n + 1);
    expect(assignNotice('n_recital', null)).toBe(true);
    expect(handlerOf(notice('n_recital'))).toBeNull();
    expect(st().audit.at(-1)?.sentence).toBe('Michael cleared who handles “Fall recital and rehearsal”');
  });

  it('is part of the exported data (it lives on the notice)', () => {
    assignNotice('n_tripform', 'm_michael');
    expect(st().exportAll().data.notices.find((x) => x.id === 'n_tripform')).toMatchObject({ handledBy: 'm_michael' });
  });
});

describe('school portals', () => {
  it('adds a read-only page watcher with an audit row', () => {
    const n = st().audit.length;
    const id = addPortal('Lakeside High', 'portal.lakesidehigh.example/parents');
    expect(id).toBeTruthy();
    expect(st().watchers.find((w) => w.id === id)).toMatchObject({ label: 'Lakeside High · portal', url: 'https://portal.lakesidehigh.example/parents', status: 'watching', spaceId: 'education' });
    expect(schoolPages(st().watchers, 'Lakeside High').map((w) => w.label)).toEqual(['Lakeside High · school calendar', 'Lakeside High · portal']);
    expect(st().audit).toHaveLength(n + 1);
    expect(st().audit.at(-1)?.code).toBe('watcher.added');
  });

  it('refuses something that is not a web address, and writes nothing', () => {
    const n = st().audit.length;
    expect(addPortal('Lakeside High', 'not a url')).toBeNull();
    expect(normalizeUrl('localhost')).toBeNull();
    expect(normalizeUrl('http://x.example')).toBe('http://x.example/');
    expect(st().audit).toHaveLength(n);
  });
});
