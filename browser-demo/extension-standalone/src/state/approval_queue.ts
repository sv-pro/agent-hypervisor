import type { ApprovalRequest, ApprovalStatus } from '../core/approval';

export type ApprovalQueue = ApprovalRequest[];

/**
 * Returns a new queue with the request appended.
 */
export function enqueue(queue: ApprovalQueue, req: ApprovalRequest): ApprovalQueue {
  return [...queue, req];
}

/**
 * Returns a new queue with the matching entry's status updated.
 * Sets resolved_at to now when the new status is 'approved' or 'denied'.
 */
export function resolve(
  queue: ApprovalQueue,
  id: string,
  status: Extract<ApprovalStatus, 'approved' | 'denied'>
): ApprovalQueue {
  return queue.map((req) =>
    req.id === id
      ? { ...req, status, resolved_at: new Date().toISOString() }
      : req
  );
}

/**
 * Returns only the pending entries.
 */
export function pendingOnly(queue: ApprovalQueue): ApprovalRequest[] {
  return queue.filter((req) => req.status === 'pending');
}
