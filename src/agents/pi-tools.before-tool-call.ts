import type { OpenClawConfig } from "../config/config.js";
import type { AnyAgentTool } from "./tools/common.js";
import { authorizeTool } from "../authz/cedar-pdp-client.js";
import {
  getDelegation,
  isDelegationExpired,
  isSubagentSessionKey,
} from "../authz/delegation-store.js";
import {
  createPendingApproval,
  computeSendRequestHash,
  isSendEmailTool,
  resolveHitlEndpoint,
  waitForApproval,
  type HumanApproval,
} from "../authz/hitl-client.js";
import { createSubsystemLogger } from "../logging/subsystem.js";
import { getGlobalHookRunner } from "../plugins/hook-runner-global.js";
import { normalizeToolName } from "./tool-policy.js";

type HookContext = {
  agentId?: string;
  sessionKey?: string;
  config?: OpenClawConfig;
};

type HookOutcome = { blocked: true; reason: string } | { blocked: false; params: unknown };

const log = createSubsystemLogger("agents/tools");

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readEmailFields(params: Record<string, unknown>): {
  to: string;
  subject: string;
  body: string;
} {
  return {
    to: typeof params.to === "string" ? params.to : "",
    subject: typeof params.subject === "string" ? params.subject : "",
    body: typeof params.body === "string" ? params.body : "",
  };
}

async function maybeWaitForHitl(args: {
  toolName: string;
  email?: { to: string; subject: string; body: string };
  requestHash?: string;
  decisionReason?: string;
  pdpConfig: {
    endpoint?: string;
    timeoutMs?: number;
    failOpen?: boolean;
    hitlEndpoint?: string;
    hitlTimeoutMs?: number;
  };
  agentId?: string;
  toolCallId?: string;
  isSubAgent: boolean;
  delegation?: {
    isDelegated: boolean;
    delegatedActions: string[];
    delegatedPathPattern?: string;
    delegatedCommandPattern?: string;
  };
  params: Record<string, unknown>;
}): Promise<{ allowed: boolean; reason?: string }> {
  const hitlEndpoint = resolveHitlEndpoint(args.pdpConfig);
  if (!isSendEmailTool(args.toolName) || !hitlEndpoint || !args.email || !args.requestHash) {
    log.info(
      `HITL skip park: tool=${args.toolName} hitlEndpoint=${hitlEndpoint ?? "unset"} hasEmail=${Boolean(args.email)} hasHash=${Boolean(args.requestHash)}`,
    );
    return {
      allowed: false,
      reason: args.decisionReason || "Tool execution denied by authorization policy",
    };
  }

  const timeoutMs = args.pdpConfig.hitlTimeoutMs ?? 180_000;
  log.info(`HITL parking send_email to=${args.email.to} timeoutMs=${timeoutMs}`);

  try {
    const pending = await createPendingApproval(hitlEndpoint, {
      to: args.email.to,
      subject: args.email.subject,
      body: args.email.body,
      requestHash: args.requestHash,
      agentId: args.agentId,
      toolCallId: args.toolCallId,
      timeoutMs,
    });
    const approval: HumanApproval | null = await waitForApproval(
      hitlEndpoint,
      pending.id,
      timeoutMs,
    );
    if (!approval) {
      return {
        allowed: false,
        reason: "Human approval timed out — send denied",
      };
    }

    const retry = await authorizeTool(
      {
        toolName: args.toolName,
        params: args.params,
        toolCallId: args.toolCallId,
        agentId: args.agentId,
        isSubAgent: args.isSubAgent,
        delegation: args.delegation,
        email: args.email,
        requestHash: args.requestHash,
        humanApproval: approval,
      },
      {
        endpoint: args.pdpConfig.endpoint ?? "",
        timeoutMs: args.pdpConfig.timeoutMs,
        failOpen: args.pdpConfig.failOpen,
      },
    );
    if (!retry.allowed) {
      return {
        allowed: false,
        reason: retry.reason || "Send denied after human approval",
      };
    }
    return { allowed: true };
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return {
      allowed: false,
      reason: `Human approval failed: ${errorMsg}`,
    };
  }
}

export async function runBeforeToolCallHook(args: {
  toolName: string;
  params: unknown;
  toolCallId?: string;
  ctx?: HookContext;
}): Promise<HookOutcome> {
  const toolName = normalizeToolName(args.toolName || "tool");
  const params = args.params;

  // Check PDP authorization first (if enabled)
  // Skip for query_authorization_constraints and delegate_authorization — meta-tools
  const pdpConfig = args.ctx?.config?.authz?.pdp;
  const skipAuthzTools = ["query_authorization_constraints", "delegate_authorization"];
  if (pdpConfig?.enabled && pdpConfig.endpoint && !skipAuthzTools.includes(toolName)) {
    try {
      const sessionKey = args.ctx?.sessionKey ?? "";
      const isSubAgent = isSubagentSessionKey(sessionKey);

      // For subagents: check delegation before calling PDP
      let delegation:
        | {
            isDelegated: boolean;
            delegatedActions: string[];
            delegatedPathPattern?: string;
            delegatedCommandPattern?: string;
          }
        | undefined;

      if (isSubAgent) {
        const record = getDelegation(sessionKey);

        // No delegation record → deny immediately
        if (!record) {
          return {
            blocked: true,
            reason: "SubAgent has no delegation record — access denied",
          };
        }

        // Expired delegation → deny immediately (PEP-enforced, no PDP call)
        if (isDelegationExpired(record)) {
          log.info(`Delegation expired: subagent=${sessionKey} id=${record.id}`);
          return {
            blocked: true,
            reason: "Delegation has expired — access denied",
          };
        }

        // Check if tool's action is in allowedActions (fast PEP check)
        if (!record.allowedActions.includes(toolName)) {
          return {
            blocked: true,
            reason: `Action "${toolName}" is not in delegation scope [${record.allowedActions.join(", ")}]`,
          };
        }

        // Build delegation context for PDP
        delegation = {
          isDelegated: true,
          delegatedActions: record.allowedActions,
          delegatedPathPattern: record.pathPattern,
          delegatedCommandPattern: record.commandPattern,
        };
      }

      const authzParams = isPlainObject(params) ? params : {};
      const email = isSendEmailTool(toolName) ? readEmailFields(authzParams) : undefined;
      const requestHash = email
        ? computeSendRequestHash({
            ...email,
            toolCallId: args.toolCallId || "unknown",
          })
        : undefined;

      const decision = await authorizeTool(
        {
          toolName,
          params: authzParams,
          toolCallId: args.toolCallId,
          agentId: args.ctx?.agentId,
          sessionKey: args.ctx?.sessionKey,
          isSubAgent,
          delegation,
          email,
          requestHash,
        },
        {
          endpoint: pdpConfig.endpoint,
          timeoutMs: pdpConfig.timeoutMs,
          failOpen: pdpConfig.failOpen,
        },
      );

      if (!decision.allowed) {
        const hitlDecision = await maybeWaitForHitl({
          toolName,
          email,
          requestHash,
          decisionReason: decision.reason,
          pdpConfig,
          agentId: args.ctx?.agentId,
          toolCallId: args.toolCallId,
          isSubAgent,
          delegation,
          params: authzParams,
        });
        if (!hitlDecision.allowed) {
          return {
            blocked: true,
            reason: hitlDecision.reason || "Tool execution denied by authorization policy",
          };
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      log.warn(`PDP check failed: tool=${toolName} error=${errorMsg}`);
      // Error handling is done inside authorizeTool (fail-open/fail-closed)
      // If we reach here, authorizeTool threw unexpectedly - fail closed
      return {
        blocked: true,
        reason: `Authorization check failed: ${errorMsg}`,
      };
    }
  }

  // Run plugin hooks (if any)
  const hookRunner = getGlobalHookRunner();
  if (!hookRunner?.hasHooks("before_tool_call")) {
    return { blocked: false, params: args.params };
  }
  try {
    const normalizedParams = isPlainObject(params) ? params : {};
    const hookResult = await hookRunner.runBeforeToolCall(
      {
        toolName,
        params: normalizedParams,
      },
      {
        toolName,
        agentId: args.ctx?.agentId,
        sessionKey: args.ctx?.sessionKey,
      },
    );

    if (hookResult?.block) {
      return {
        blocked: true,
        reason: hookResult.blockReason || "Tool call blocked by plugin hook",
      };
    }

    if (hookResult?.params && isPlainObject(hookResult.params)) {
      if (isPlainObject(params)) {
        return { blocked: false, params: { ...params, ...hookResult.params } };
      }
      return { blocked: false, params: hookResult.params };
    }
  } catch (err) {
    const toolCallId = args.toolCallId ? ` toolCallId=${args.toolCallId}` : "";
    log.warn(`before_tool_call hook failed: tool=${toolName}${toolCallId} error=${String(err)}`);
  }

  return { blocked: false, params };
}

export function wrapToolWithBeforeToolCallHook(
  tool: AnyAgentTool,
  ctx?: HookContext,
): AnyAgentTool {
  const execute = tool.execute;
  if (!execute) {
    return tool;
  }
  const toolName = tool.name || "tool";
  return {
    ...tool,
    execute: async (toolCallId, params, signal, onUpdate) => {
      const outcome = await runBeforeToolCallHook({
        toolName,
        params,
        toolCallId,
        ctx,
      });
      if (outcome.blocked) {
        throw new Error(outcome.reason);
      }
      return await execute(toolCallId, outcome.params, signal, onUpdate);
    },
  };
}

export const __testing = {
  runBeforeToolCallHook,
  isPlainObject,
};
