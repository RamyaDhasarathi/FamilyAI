// The web mocks are copies of the mobile ones; these pin the behaviour both apps share.
import { describe, expect, it } from 'vitest';
import { needsItems } from './data';
import { headlineItem, moodOf, scenarioItems, sortNeeds, summaryCount } from './scenarios';
import { replyTo } from './chatReplies';
import { checks } from '../family/region';

const pick = (ids: string[]) => needsItems.filter((n) => ids.includes(n.id));

describe('scenarios', () => {
  it('derive the mood from the most severe open item', () => {
    expect(moodOf([])).toBe('calm');
    expect(moodOf(pick(scenarioItems.insight))).toBe('insight');
    expect(moodOf(pick(scenarioItems.headsup))).toBe('headsup');
    expect(moodOf(pick(scenarioItems.urgent))).toBe('urgent');
  });

  it('word the summary line like the video', () => {
    expect(summaryCount(pick(scenarioItems.urgent))).toEqual({ n: 3, word: 'urgent' });
    expect(summaryCount(pick(scenarioItems.headsup))).toEqual({ n: 7, word: 'need you' });
    expect(summaryCount(pick(scenarioItems.insight))).toEqual({ n: 1, word: 'needs you' });
  });

  it('put the unfamiliar charge first in urgent', () => {
    expect(headlineItem(pick(scenarioItems.urgent))?.id).toBe('n2');
    expect(sortNeeds(pick(scenarioItems.urgent))[0].severity).toBe('urgent');
  });
});

describe('chat replies', () => {
  it('answer by keyword per thread', () => {
    const ctx = { scenario: 'calm' as const, openCount: 0 };
    expect(replyTo('home', 'What needs me today?', ctx)).toBe('Nothing needs you right now.');
    expect(replyTo('finance', 'Show upcoming bills', ctx)).toMatch(/mortgage/);
    expect(replyTo('calendar', 'Tell me more about: x', ctx)).toMatch(/undo it/);
  });
});

describe('family field checks', () => {
  it('validate the ABA routing checksum', () => {
    expect(checks.routing('111000614')).toBeNull();
    expect(checks.routing('111000615')).not.toBeNull();
  });
});
