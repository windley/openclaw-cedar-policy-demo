import { Type } from "@sinclair/typebox";
import type { OpenClawConfig } from "../../config/config.js";
import { loadConfig } from "../../config/config.js";
import { queryConstraints } from "../../authz/cedar-pdp-client.js";
import type { AnyAgentTool } from "./common.js";
import { jsonResult, readStringParam } from "./common.js";

const QueryAuthzSchema = Type.Object({
  action: Type.String(),
});

const ACTION_MAP: Record<string, string> = {
  write: "write",
  read: "read",
  bash: "bash",
  edit: "edit",
  exec: "bash",
};

export function createQueryAuthzTool(opts?: {
  config?: OpenClawConfig;
  agentId?: string;
}): AnyAgentTool {
  return {
    label: "Query Authorization Constraints",
    name: "query_authorization_constraints",
    description:
      "Query what operations are allowed by the authorization system. Use this BEFORE attempting file or command operations to discover what's permitted and what constraints apply. Pass an action like 'write', 'read', 'bash', or 'edit'.",
    parameters: QueryAuthzSchema,
    execute: async (_toolCallId, args) => {
      const params = args as Record<string, unknown>;
      const cfg = opts?.config ?? loadConfig();
      const endpoint = cfg.authz?.pdp?.queryConstraintsEndpoint;

      if (!endpoint) {
        throw new Error("queryConstraintsEndpoint not configured");
      }

      const rawAction = readStringParam(params, "action", { required: true });
      const toolName = ACTION_MAP[rawAction.toLowerCase()] ?? rawAction.toLowerCase();

      const result = await queryConstraints(toolName, {
        queryConstraintsEndpoint: endpoint,
        timeoutMs: cfg.authz?.pdp?.timeoutMs,
        agentId: opts?.agentId,
      });

      // Format residuals into a readable summary
      const summary = result.residuals.length > 0
        ? result.residuals.map((r, i) => `[Policy ${i + 1}]\n${r}`).join("\n\n")
        : "No residual policies returned — the action may be unconditionally allowed or denied.";

      return jsonResult({
        action: toolName,
        decision: result.decision,
        constraintCount: result.residuals.length,
        constraints: summary,
        explanation: result.explanation,
      });
    },
  };
}
