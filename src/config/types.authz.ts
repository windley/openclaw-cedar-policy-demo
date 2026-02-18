/**
 * Authorization configuration types.
 */

export type AuthzConfig = {
  /**
   * Policy Decision Point (PDP) configuration for Cedar-based authorization.
   */
  pdp?: {
    /**
     * Enable PDP-based tool authorization (default: false).
     */
    enabled?: boolean;
    /**
     * PDP endpoint URL (e.g., "http://localhost:8180/authorize").
     * Required when enabled is true.
     */
    endpoint?: string;
    /**
     * Request timeout in milliseconds (default: 2000).
     */
    timeoutMs?: number;
    /**
     * Fail-open mode: allow tool execution if PDP is unreachable (default: false).
     * When false (fail-closed), unreachable PDP will deny all tool executions.
     */
    failOpen?: boolean;
    /**
     * TPE query-constraints endpoint URL (e.g., "http://localhost:8180/query-constraints").
     * Enables the query_authorization_constraints tool for proactive policy discovery.
     */
    queryConstraintsEndpoint?: string;
  };
};
