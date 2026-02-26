// Cedar Delegation Policies for OpenClaw SubAgent Authorization
//
// These policies enforce delegation-as-data: a main agent can grant a subset
// of its permissions to a subagent via a delegation record. The PEP injects
// delegation context attributes before calling the PDP.
//
// Design: Cedar has no `now()` function, so time-based expiry (TTL) is
// enforced by the PEP *before* calling Cedar. By the time these policies
// evaluate, expired delegations have already been rejected.
//
// All optional attributes are guarded with `has` checks for strict validation.

//
// Delegation Policy 1: Allow delegated subagents to perform actions in their delegation scope
// The PEP populates isDelegated, delegatedActions, and optionally delegatedPathPattern
// and delegatedCommandPattern from the delegation record.
//
@id("delegation-1-allow-delegated-actions")
permit(
  principal is OpenClaw::SubAgent,
  action,
  resource
)
when {
  context has isDelegated && context.isDelegated == true &&
  context has delegatedActions &&
  (
    // Map Cedar actions back to delegation action names for set membership check
    (action == OpenClaw::Action::"ToolExec::Read" && context.delegatedActions.contains("read")) ||
    (action == OpenClaw::Action::"ToolExec::Write" && context.delegatedActions.contains("write")) ||
    (action == OpenClaw::Action::"ToolExec::Edit" && context.delegatedActions.contains("edit")) ||
    (action == OpenClaw::Action::"ToolExec::Bash" && context.delegatedActions.contains("bash")) ||
    (action == OpenClaw::Action::"ToolExec::Exec" && context.delegatedActions.contains("exec")) ||
    (action == OpenClaw::Action::"ToolExec::Glob" && context.delegatedActions.contains("glob")) ||
    (action == OpenClaw::Action::"ToolExec::Grep" && context.delegatedActions.contains("grep")) ||
    (action == OpenClaw::Action::"ToolExec::Process" && context.delegatedActions.contains("process")) ||
    (action == OpenClaw::Action::"ToolExec::ApplyPatch" && context.delegatedActions.contains("apply_patch"))
  )
};

//
// Delegation Policy 2: Enforce path constraints on delegated file operations
// If the delegation specifies a path pattern, file operations must match it.
//
@id("delegation-2-enforce-path-constraint")
forbid(
  principal is OpenClaw::SubAgent,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit",
    OpenClaw::Action::"ToolExec::Glob",
    OpenClaw::Action::"ToolExec::Grep"
  ],
  resource
)
when {
  context has isDelegated && context.isDelegated == true &&
  context has delegatedPathPattern &&
  context has filePath &&
  // Deny if the file path doesn't match the delegated path pattern.
  // Cedar's `like` only works with string literals, so we enumerate common patterns.
  // The PEP normalizes the path pattern into the delegatedPathPattern field.
  !(
    (context.delegatedPathPattern == "/tmp/*" && context.filePath like "/tmp/*") ||
    (context.delegatedPathPattern == "/var/tmp/*" && context.filePath like "/var/tmp/*") ||
    (context.delegatedPathPattern == "/home/*" && context.filePath like "/home/*") ||
    (context.delegatedPathPattern == "/Users/*" && context.filePath like "/Users/*") ||
    (context.delegatedPathPattern == "./*" && context.filePath like "./*")
  )
};

//
// Delegation Policy 3: Enforce command constraints on delegated bash operations
// If the delegation specifies a command pattern, bash/exec must match it.
//
@id("delegation-3-enforce-command-constraint")
forbid(
  principal is OpenClaw::SubAgent,
  action in [
    OpenClaw::Action::"ToolExec::Bash",
    OpenClaw::Action::"ToolExec::Exec"
  ],
  resource
)
when {
  context has isDelegated && context.isDelegated == true &&
  context has delegatedCommandPattern &&
  context has command &&
  !(
    (context.delegatedCommandPattern == "git *" && context.command like "git *") ||
    (context.delegatedCommandPattern == "ls *" && context.command like "ls *") ||
    (context.delegatedCommandPattern == "cat *" && context.command like "cat *") ||
    (context.delegatedCommandPattern == "grep *" && context.command like "grep *") ||
    (context.delegatedCommandPattern == "find *" && context.command like "find *") ||
    (context.delegatedCommandPattern == "echo *" && context.command like "echo *")
  )
};

//
// Delegation Policy 4: Deny subagents any action not covered by a delegation
// If a subagent has no delegation context, deny everything.
//
@id("delegation-4-deny-undelegated-subagents")
forbid(
  principal is OpenClaw::SubAgent,
  action,
  resource
)
when {
  !(context has isDelegated) || (context has isDelegated && context.isDelegated == false)
};

//
// Delegation Policy 5: Deny subagent actions outside delegation scope
// Even when isDelegated is true, forbid any action not listed in delegatedActions.
// This overrides base permit policies that use `principal` (which matches SubAgent
// via entity hierarchy).
//
@id("delegation-5-deny-out-of-scope-actions")
forbid(
  principal is OpenClaw::SubAgent,
  action,
  resource
)
when {
  context has isDelegated && context.isDelegated == true &&
  context has delegatedActions &&
  !(
    (action == OpenClaw::Action::"ToolExec::Read" && context.delegatedActions.contains("read")) ||
    (action == OpenClaw::Action::"ToolExec::Write" && context.delegatedActions.contains("write")) ||
    (action == OpenClaw::Action::"ToolExec::Edit" && context.delegatedActions.contains("edit")) ||
    (action == OpenClaw::Action::"ToolExec::Bash" && context.delegatedActions.contains("bash")) ||
    (action == OpenClaw::Action::"ToolExec::Exec" && context.delegatedActions.contains("exec")) ||
    (action == OpenClaw::Action::"ToolExec::Glob" && context.delegatedActions.contains("glob")) ||
    (action == OpenClaw::Action::"ToolExec::Grep" && context.delegatedActions.contains("grep")) ||
    (action == OpenClaw::Action::"ToolExec::Process" && context.delegatedActions.contains("process")) ||
    (action == OpenClaw::Action::"ToolExec::ApplyPatch" && context.delegatedActions.contains("apply_patch"))
  )
};
