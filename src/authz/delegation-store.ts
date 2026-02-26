/**
 * In-memory delegation store for subagent authorization.
 *
 * A delegation record grants a subagent a subset of the main agent's permissions.
 * The PEP reads delegations from this store and injects them into Cedar context
 * before calling the PDP.
 *
 * Time-based expiry is enforced here (PEP-side) because Cedar has no `now()` function.
 */

import { randomUUID } from "node:crypto";

export type DelegationRecord = {
  /** Unique delegation ID */
  id: string;
  /** Main agent's session key (the delegator) */
  delegatorSessionKey: string;
  /** Child session key (e.g., "agent:main:subagent:<uuid>") */
  subagentSessionKey: string;
  /** Actions the subagent is allowed to perform (e.g., ["read", "write"]) */
  allowedActions: string[];
  /** Optional file path glob constraint (e.g., "/tmp/*") */
  pathPattern?: string;
  /** Optional command glob constraint (e.g., "git *") */
  commandPattern?: string;
  /** Optional expiry timestamp in ms since epoch — enforced by PEP, not Cedar */
  expiresAt?: number;
  /** When this delegation was created */
  createdAt: number;
};

// In-memory store keyed by subagent session key
const delegations = new Map<string, DelegationRecord>();

/**
 * Create a new delegation record granting permissions to a subagent.
 */
export function createDelegation(
  record: Omit<DelegationRecord, "id" | "createdAt">,
): DelegationRecord {
  const delegation: DelegationRecord = {
    ...record,
    id: randomUUID(),
    createdAt: Date.now(),
  };
  delegations.set(delegation.subagentSessionKey, delegation);
  return delegation;
}

/**
 * Look up a delegation by subagent session key.
 */
export function getDelegation(subagentSessionKey: string): DelegationRecord | undefined {
  return delegations.get(subagentSessionKey);
}

/**
 * Revoke a delegation by ID.
 */
export function revokeDelegation(id: string): boolean {
  for (const [key, record] of delegations) {
    if (record.id === id) {
      delegations.delete(key);
      return true;
    }
  }
  return false;
}

/**
 * Check if a delegation has expired. Enforced by the PEP before calling Cedar.
 */
export function isDelegationExpired(record: DelegationRecord): boolean {
  if (record.expiresAt === undefined) return false;
  return Date.now() > record.expiresAt;
}

/**
 * Check if a session key looks like a subagent session key.
 * Convention: subagent keys contain ":subagent:" segment.
 */
export function isSubagentSessionKey(sessionKey: string): boolean {
  return sessionKey.includes(":subagent:");
}

/**
 * Clear all delegations (for testing).
 */
export function clearDelegations(): void {
  delegations.clear();
}

export const __testing = {
  delegations,
  clearDelegations,
};
