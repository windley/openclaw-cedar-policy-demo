import type { AnyAgentTool } from "./tools/common.js";
import type { OpenClawConfig } from "../config/config.js";
import { authorizeTool } from "../authz/cedar-pdp-client.js";
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

export async function runBeforeToolCallHook(args: {
  toolName: string;
  params: unknown;
  toolCallId?: string;
  ctx?: HookContext;
}): Promise<HookOutcome> {
  const toolName = normalizeToolName(args.toolName || "tool");
  const params = args.params;

  // Check PDP authorization first (if enabled)
  const pdpConfig = args.ctx?.config?.authz?.pdp;
  if (pdpConfig?.enabled && pdpConfig.endpoint) {
    try {
      const decision = await authorizeTool(
        {
          toolName,
          params: isPlainObject(params) ? params : {},
          toolCallId: args.toolCallId,
          agentId: args.ctx?.agentId,
          sessionKey: args.ctx?.sessionKey,
        },
        {
          endpoint: pdpConfig.endpoint,
          timeoutMs: pdpConfig.timeoutMs,
          failOpen: pdpConfig.failOpen,
        },
      );

      if (!decision.allowed) {
        return {
          blocked: true,
          reason: decision.reason || "Tool execution denied by authorization policy",
        };
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
