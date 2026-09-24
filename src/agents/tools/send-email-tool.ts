import { Type } from "@sinclair/typebox";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { AnyAgentTool } from "./common.js";
import { jsonResult, readStringParam } from "./common.js";

const SendEmailSchema = Type.Object({
  to: Type.String(),
  subject: Type.String(),
  body: Type.String(),
});

const MAILBOX_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../demo/mailbox/sent",
);

function mailboxFilename(sentAt: Date): string {
  return `${sentAt.toISOString().replaceAll(":", "")}.json`;
}

export function createSendEmailTool(): AnyAgentTool {
  return {
    label: "Send Email",
    name: "send_email",
    description:
      "Send a simulated email. Delivery writes a JSON file to the local mailbox sink after human Yubikey approval. Pass to, subject, and body. Do not send mail via bash or other tools.",
    parameters: SendEmailSchema,
    execute: async (_toolCallId, args) => {
      const params = args as Record<string, unknown>;
      const to = readStringParam(params, "to", { required: true });
      const subject = readStringParam(params, "subject", { required: true });
      const body = readStringParam(params, "body", { required: true, allowEmpty: true });
      const sentAt = new Date();
      await fs.mkdir(MAILBOX_DIR, { recursive: true });
      let filename = mailboxFilename(sentAt);
      let target = path.join(MAILBOX_DIR, filename);
      if (await exists(target)) {
        filename = `${sentAt.toISOString().replaceAll(":", "")}-${_toolCallId || "dup"}.json`;
        target = path.join(MAILBOX_DIR, filename);
      }
      const message = {
        to,
        subject,
        body,
        sentAt: sentAt.toISOString(),
        filename,
      };
      await fs.writeFile(target, `${JSON.stringify(message, null, 2)}\n`, "utf8");
      return jsonResult({
        status: "sent",
        mailbox: target,
        ...message,
      });
    },
  };
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}
