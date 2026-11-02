// A removal confirmed on a member's profile is animated on the hub (mobile:
// popTo('Family', { remove })). The profile queues it here, goes back, and
// the hub takes it when it mounts.
export interface PendingRemoval {
  id: string;
  reassign?: string | null;
}

let pending: PendingRemoval | null = null;

export function queueRemoval(r: PendingRemoval) {
  pending = r;
}

export function takeRemoval(): PendingRemoval | null {
  const r = pending;
  pending = null;
  return r;
}
