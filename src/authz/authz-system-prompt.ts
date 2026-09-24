export function buildAuthzSystemPrompt(params: {
  extraSystemPrompt?: string;
  pdpEnabled?: boolean;
  queryConstraintsEnabled?: boolean;
  isSubagent: boolean;
}): string | undefined {
  if (!params.pdpEnabled) {
    return params.extraSystemPrompt;
  }

  const lines = [
    params.extraSystemPrompt?.trim(),
    "## Authorization Policy",
    "This system uses Cedar authorization policies.",
  ];

  if (params.queryConstraintsEnabled) {
    lines.push(
      "You have a `query_authorization_constraints` tool available.",
      "IMPORTANT: When you need to perform file operations (read, write, edit) or run commands (bash), use the `query_authorization_constraints` tool FIRST to discover what is permitted. Do NOT read policy files directly from disk to determine permissions - always use the tool, which queries the live policy decision point.",
      "Pass the relevant action type: 'write', 'read', 'bash', or 'edit'.",
      params.isSubagent
        ? "You are a delegated subagent. Your permissions are a restricted subset of the main agent's permissions. Use `query_authorization_constraints` to discover what you are allowed to do before attempting any operations. Do not assume you have the same access as the main agent."
        : "When spawning subagents with `sessions_spawn`, use `delegate_authorization` FIRST to grant the subagent only the permissions it needs. Specify the subagent session key, allowed actions, and optionally a path or command pattern and TTL.",
    );
  }

  lines.push(
    "Sending email requires a human Yubikey approval. Use the `send_email` tool with `to`, `subject`, and `body`. The send waits for a human to approve it on the approver page; if nobody approves before timeout, the send is denied and you must not retry that same send automatically. Drafting (writing a body to a file, reading sources) does not require approval. Do not send mail via bash, gog, or other tools.",
  );

  return lines.filter(Boolean).join("\n");
}
