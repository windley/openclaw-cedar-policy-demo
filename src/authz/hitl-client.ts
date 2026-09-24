import { createHash } from "node:crypto";
import { createSubsystemLogger } from "../logging/subsystem.js";

const log = createSubsystemLogger("authz/hitl");

export type HumanApproval = {
  verified: boolean;
  method: string;
  requestHash: string;
};

export type HitlPendingRequest = {
  to: string;
  subject: string;
  body: string;
  requestHash: string;
  agentId?: string;
  toolCallId?: string;
  timeoutMs: number;
};

export function computeSendRequestHash(input: {
  to: string;
  subject: string;
  body: string;
  toolCallId: string;
}): string {
  const canonical = JSON.stringify({
    body: input.body,
    subject: input.subject,
    to: input.to,
    toolCallId: input.toolCallId,
    toolName: "send_email",
  });
  return createHash("sha256").update(canonical).digest("hex");
}

export function isSendEmailTool(toolName: string): boolean {
  return toolName === "send_email";
}

/** Prefer explicit hitlEndpoint; otherwise use the PDP origin. */
export function resolveHitlEndpoint(pdpConfig: {
  hitlEndpoint?: string;
  endpoint?: string;
}): string | undefined {
  if (pdpConfig.hitlEndpoint?.trim()) {
    return pdpConfig.hitlEndpoint.trim().replace(/\/$/, "");
  }
  if (!pdpConfig.endpoint) {
    return undefined;
  }
  try {
    return new URL(pdpConfig.endpoint).origin;
  } catch {
    return undefined;
  }
}

export async function createPendingApproval(
  endpoint: string,
  request: HitlPendingRequest,
): Promise<{ id: string }> {
  const response = await fetch(new URL("/approvals", endpoint).toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "unknown error");
    throw new Error(`HITL create failed: HTTP ${response.status} ${text}`);
  }
  const payload = (await response.json()) as { id?: string };
  if (!payload.id) {
    throw new Error("HITL create failed: missing approval id");
  }
  log.info(`HITL pending send id=${payload.id} to=${request.to}`);
  return { id: payload.id };
}

export async function waitForApproval(
  endpoint: string,
  approvalId: string,
  timeoutMs: number,
): Promise<HumanApproval | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs + 5_000);
  try {
    const url = new URL(`/approvals/${encodeURIComponent(approvalId)}/wait`, endpoint);
    const response = await fetch(url.toString(), { signal: controller.signal });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as {
      status?: string;
      humanApproval?: HumanApproval;
    };
    if (payload.status === "approved" && payload.humanApproval?.verified) {
      return payload.humanApproval;
    }
    log.info(`HITL wait ended without approval: id=${approvalId} status=${payload.status}`);
    return null;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log.warn(`HITL wait failed: id=${approvalId} error=${message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
