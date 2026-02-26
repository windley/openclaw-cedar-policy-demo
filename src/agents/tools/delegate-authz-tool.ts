import { Type } from "@sinclair/typebox";
import type { OpenClawConfig } from "../../config/config.js";
import {
  createDelegation,
  isSubagentSessionKey,
} from "../../authz/delegation-store.js";
import type { AnyAgentTool } from "./common.js";
import { jsonResult, readNumberParam, readStringArrayParam, readStringParam } from "./common.js";

const DelegateAuthzSchema = Type.Object({
  subagentSessionKey: Type.String(),
  allowedActions: Type.Array(Type.String()),
  pathPattern: Type.Optional(Type.String()),
  commandPattern: Type.Optional(Type.String()),
  ttlSeconds: Type.Optional(Type.Number()),
});

export function createDelegateAuthzTool(opts?: {
  config?: OpenClawConfig;
  agentSessionKey?: string;
}): AnyAgentTool {
  return {
    label: "Delegate Authorization",
    name: "delegate_authorization",
    description:
      "Create a delegation record granting a subagent specific permissions. " +
      "Use before sessions_spawn to scope what the subagent can do. " +
      "Pass the subagent session key, allowed actions (e.g., ['read', 'write']), " +
      "and optionally a path pattern (e.g., '/tmp/*') or command pattern (e.g., 'git *') " +
      "and a TTL in seconds.",
    parameters: DelegateAuthzSchema,
    execute: async (_toolCallId, args) => {
      const params = args as Record<string, unknown>;

      // Only main agents can create delegations
      const callerKey = opts?.agentSessionKey ?? "";
      if (isSubagentSessionKey(callerKey)) {
        throw new Error("SubAgents cannot create delegations — only the main agent can delegate");
      }

      const subagentSessionKey = readStringParam(params, "subagentSessionKey", { required: true });
      const allowedActions = readStringArrayParam(params, "allowedActions", { required: true });
      const pathPattern = readStringParam(params, "pathPattern");
      const commandPattern = readStringParam(params, "commandPattern");
      const ttlSeconds = readNumberParam(params, "ttlSeconds");

      const expiresAt = ttlSeconds ? Date.now() + ttlSeconds * 1000 : undefined;

      const record = createDelegation({
        delegatorSessionKey: callerKey,
        subagentSessionKey,
        allowedActions,
        pathPattern,
        commandPattern,
        expiresAt,
      });

      return jsonResult({
        delegationId: record.id,
        subagentSessionKey: record.subagentSessionKey,
        allowedActions: record.allowedActions,
        pathPattern: record.pathPattern ?? null,
        commandPattern: record.commandPattern ?? null,
        expiresAt: record.expiresAt
          ? new Date(record.expiresAt).toISOString()
          : null,
        message: "Delegation created. The subagent can now perform the specified actions.",
      });
    },
  };
}
