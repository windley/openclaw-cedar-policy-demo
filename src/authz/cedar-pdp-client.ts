/**
 * Cedar Policy Decision Point (PDP) client for tool authorization.
 *
 * This module provides a client for calling an external Cedar-based PDP
 * (cedar-agent) to authorize tool executions before they run.
 */

import { createSubsystemLogger } from "../logging/subsystem.js";

const log = createSubsystemLogger("authz/cedar-pdp");

/**
 * Cedar authorization request format.
 */
export type CedarAuthzRequest = {
  /** Principal making the request (e.g., "Agent::\"agent123\"") */
  principal: string;
  /** Action being performed (e.g., "Action::\"ToolExec::Bash\"") */
  action: string;
  /** Resource being accessed (e.g., "Tool::\"bash\"") */
  resource: string;
  /** Additional context attributes */
  context?: Record<string, unknown>;
};

/**
 * Cedar authorization response format.
 */
export type CedarAuthzResponse = {
  /** Authorization decision */
  decision: "Allow" | "Deny";
  /** Diagnostic information */
  diagnostics?: {
    /** Policy IDs that led to this decision */
    reason?: string[];
    /** Any errors during evaluation */
    errors?: string[];
  };
};

/**
 * PDP client configuration.
 */
export type CedarPdpConfig = {
  /** PDP endpoint URL (e.g., "http://localhost:8180/authorize") */
  endpoint: string;
  /** Request timeout in milliseconds (default: 2000) */
  timeoutMs?: number;
  /** Whether to fail open (allow) on PDP errors (default: false - fail closed) */
  failOpen?: boolean;
};

/**
 * Tool execution context for authorization.
 */
export type ToolAuthzContext = {
  /** Tool name being executed */
  toolName: string;
  /** Tool parameters */
  params: Record<string, unknown>;
  /** Tool call ID */
  toolCallId?: string;
  /** Agent ID */
  agentId?: string;
  /** Session key */
  sessionKey?: string;
  /** Additional context attributes */
  attributes?: Record<string, unknown>;
};

/**
 * Authorization decision result.
 */
export type AuthzDecision = {
  /** Whether the tool execution is allowed */
  allowed: boolean;
  /** Denial reason (if denied) */
  reason?: string;
  /** Matched policy IDs */
  policies?: string[];
};

/**
 * Build a Cedar principal identifier from agent context.
 */
function buildPrincipal(ctx: ToolAuthzContext): string {
  // Use agentId if available, otherwise use sessionKey, otherwise use "unknown"
  const identifier = ctx.agentId || ctx.sessionKey || "unknown";
  return `OpenClaw::Agent::"${identifier}"`;
}

/**
 * Build a Cedar action identifier from tool name.
 */
function buildAction(toolName: string): string {
  // Normalize tool name to PascalCase for Cedar action
  const normalized = toolName
    .split(/[-_]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
  return `OpenClaw::Action::"ToolExec::${normalized}"`;
}

/**
 * Build a Cedar resource identifier from tool name.
 */
function buildResource(toolName: string): string {
  return `OpenClaw::Tool::"${toolName}"`;
}

/**
 * Build Cedar context attributes from tool execution context.
 */
function buildContext(ctx: ToolAuthzContext): Record<string, unknown> {
  const context: Record<string, unknown> = {
    toolCallId: ctx.toolCallId || "unknown",
    // Always include both filePath and command (Cedar schema requires them)
    filePath: (ctx.params.path || ctx.params.file_path || "") as string,
    command: (ctx.params.command || "") as string,
    ...ctx.attributes,
  };

  // Add session context
  if (ctx.sessionKey) {
    context.sessionKey = ctx.sessionKey;
  }

  return context;
}

/**
 * Call the Cedar PDP to authorize a tool execution.
 */
export async function authorizeTool(
  ctx: ToolAuthzContext,
  config: CedarPdpConfig,
): Promise<AuthzDecision> {
  const timeoutMs = config.timeoutMs ?? 2000;
  const failOpen = config.failOpen ?? false;

  // Build Cedar authorization request
  const request: CedarAuthzRequest = {
    principal: buildPrincipal(ctx),
    action: buildAction(ctx.toolName),
    resource: buildResource(ctx.toolName),
    context: buildContext(ctx),
  };

  log.debug(
    `PDP request: tool=${ctx.toolName} principal=${request.principal} action=${request.action}`,
  );

  try {
    // Call PDP with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const response = await fetch(config.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "unknown error");
      throw new Error(`PDP HTTP ${response.status}: ${errorText}`);
    }

    const result = (await response.json()) as CedarAuthzResponse;

    if (result.decision === "Allow") {
      log.debug(
        `PDP allowed: tool=${ctx.toolName} policies=${result.diagnostics?.reason?.join(", ") || "none"}`,
      );
      return {
        allowed: true,
        policies: result.diagnostics?.reason,
      };
    }

    // Denied
    const reason =
      result.diagnostics?.errors?.[0] ||
      `Tool execution denied by policy: ${result.diagnostics?.reason?.join(", ") || "unknown"}`;

    log.info(`PDP denied: tool=${ctx.toolName} reason=${reason}`);
    return {
      allowed: false,
      reason,
      policies: result.diagnostics?.reason,
    };
  } catch (err) {
    // Handle PDP errors
    const errorMsg = err instanceof Error ? err.message : String(err);
    log.warn(`PDP error: tool=${ctx.toolName} error=${errorMsg}`);

    if (failOpen) {
      log.warn(`PDP fail-open: allowing tool=${ctx.toolName} due to error`);
      return {
        allowed: true,
        reason: `PDP error (fail-open): ${errorMsg}`,
      };
    }

    // Fail closed - deny on error
    log.warn(`PDP fail-closed: denying tool=${ctx.toolName} due to error`);
    return {
      allowed: false,
      reason: `Authorization service unavailable: ${errorMsg}`,
    };
  }
}

/**
 * Response from the TPE query-constraints endpoint.
 */
export type CedarQueryConstraintsResponse = {
  /** TPE decision (typically "UNKNOWN" with residuals) */
  decision: string;
  /** Residual Cedar policies that express remaining constraints */
  residuals: string[];
  /** Human-readable explanation */
  explanation?: string;
};

/**
 * Query authorization constraints using Cedar TPE (Typed Partial Evaluation).
 *
 * Returns residual policies that describe what conditions must be met for
 * an action to be allowed, without providing specific context values.
 */
export async function queryConstraints(
  action: string,
  config: { queryConstraintsEndpoint: string; timeoutMs?: number; agentId?: string },
): Promise<CedarQueryConstraintsResponse> {
  const timeoutMs = config.timeoutMs ?? 2000;
  const agentId = config.agentId ?? "main";

  // Build Cedar entity IDs matching the PDP server's expected format
  const principal = `OpenClaw::Agent::"${agentId}"`;
  const cedarAction = buildAction(action);
  const resource = buildResource(action);

  const request: CedarAuthzRequest = {
    principal,
    action: cedarAction,
    resource,
  };

  log.debug(`TPE query: action=${action} principal=${principal}`);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(config.queryConstraintsEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "unknown error");
      throw new Error(`TPE HTTP ${response.status}: ${errorText}`);
    }

    const result = (await response.json()) as CedarQueryConstraintsResponse;
    log.debug(`TPE result: ${result.residuals.length} residual policies`);
    return result;
  } catch (err) {
    clearTimeout(timeoutId);
    const errorMsg = err instanceof Error ? err.message : String(err);
    log.warn(`TPE query error: ${errorMsg}`);
    throw new Error(`Authorization constraint query failed: ${errorMsg}`);
  }
}

/**
 * Check if PDP is configured and enabled.
 */
export function isPdpEnabled(config?: CedarPdpConfig | null): config is CedarPdpConfig {
  return Boolean(config?.endpoint);
}

export const __testing = {
  buildPrincipal,
  buildAction,
  buildResource,
  buildContext,
};