// The collecting layer by itself: Android runs this about every 15 minutes (its minimum) while at least one source is
// switched on, even with the app closed (expo-background-task, on WorkManager). It is the same collectNow the Data
// sources screen runs, so the marks, the backend's rules (no one-time codes, notifications only from switched-on apps)
// and the local cache are the same. Defined when the bundle loads (index.ts imports this file first), as the task
// manager requires; nothing runs without a session or with every source off.
import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';
import { API_ENABLED, loadToken } from './api';
import { canCollect, collectNow, loadSettings, syncLiveSms, type CollectSettings } from './collect';

export const COLLECT_TASK = 'familyos-collect';
const EVERY_MINUTES = 15;

TaskManager.defineTask(COLLECT_TASK, async () => {
  try {
    if (!API_ENABLED || !canCollect || !(await loadToken())) return BackgroundTask.BackgroundTaskResult.Success;
    const s = await loadSettings();
    await syncLiveSms(s).catch(() => undefined); // live SMS back on if Android stopped it
    if (Object.values(s.sources).some(Boolean)) await collectNow(s);
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

/** Schedule the background run when any source is on; stop it when none is. */
export async function scheduleCollect(s: CollectSettings): Promise<void> {
  if (!canCollect) return;
  await syncLiveSms(s).catch(() => undefined);
  const on = Object.values(s.sources).some(Boolean);
  const registered = await TaskManager.isTaskRegisteredAsync(COLLECT_TASK);
  if (on && !registered) await BackgroundTask.registerTaskAsync(COLLECT_TASK, { minimumInterval: EVERY_MINUTES });
  if (!on && registered) await BackgroundTask.unregisterTaskAsync(COLLECT_TASK);
}
