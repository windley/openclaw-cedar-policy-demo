// Cedar Policies for OpenClaw Tool Authorization (TPE Version)
// These policies are optimized for Typed Partial Evaluation (TPE) with optional context attributes.
// They use `has` operator to check for attribute existence before access.

//
// Policy 1: Allow all read-only tools (safe operations)
//
@id("policy-1-allow-readonly")
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Glob",
    OpenClaw::Action::"ToolExec::Grep"
  ],
  resource
);

//
// Policy 2: Allow file write operations to /tmp directory only
//
@id("policy-2-allow-tmp-writes")
permit(
  principal,
  action == OpenClaw::Action::"ToolExec::Write",
  resource
)
when {
  context has filePath && (
    context.filePath like "/tmp/*" ||
    context.filePath like "/var/tmp/*"
  )
};

//
// Policy 3: Deny writes to sensitive system directories
//
@id("policy-3-deny-system-writes")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit"
  ],
  resource
)
when {
  context has filePath && (
    context.filePath like "/etc/*" ||
    context.filePath like "/usr/*" ||
    context.filePath like "/bin/*" ||
    context.filePath like "/sbin/*" ||
    context.filePath == "/etc/passwd" ||
    context.filePath == "/etc/shadow"
  )
};

//
// Policy 4: Allow safe bash/exec commands (list, inspect, read-only)
//
@id("policy-4-allow-safe-bash")
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Bash",
    OpenClaw::Action::"ToolExec::Exec"
  ],
  resource
)
when {
  context has command && (
    // Allow commands that start with safe read-only operations
    context.command like "ls *" ||
    context.command like "cat *" ||
    context.command like "grep *" ||
    context.command like "find *" ||
    context.command like "echo *" ||
    context.command like "pwd*" ||
    context.command like "whoami*" ||
    context.command like "date*" ||
    context.command like "git status*" ||
    context.command like "git log*" ||
    context.command like "git diff*"
  )
};

//
// Policy 5: Deny dangerous bash/exec commands
//
@id("policy-5-deny-dangerous-bash")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Bash",
    OpenClaw::Action::"ToolExec::Exec"
  ],
  resource
)
when {
  context has command && (
    // Block commands that could cause data loss or system damage
    context.command like "*rm -rf*" ||
    context.command like "*dd if=*" ||
    context.command like "*mkfs*" ||
    context.command like "*> /dev/*" ||
    (context.command like "*curl*" && context.command like "*| sh*") ||
    (context.command like "*wget*" && context.command like "*| sh*") ||
    context.command like "*chmod 777*" ||
    context.command like "*chown root*" ||
    context.command like "*sudo su*" ||
    context.command like "*shutdown*" ||
    context.command like "*reboot*" ||
    context.command like "*init 0*"
  )
};

//
// Policy 6: Allow git operations (development workflow)
//
@id("policy-6-allow-git-ops")
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Bash",
    OpenClaw::Action::"ToolExec::Exec"
  ],
  resource
)
when {
  context has command &&
  context.command like "git *" &&
  (
    context.command like "*git add*" ||
    context.command like "*git commit*" ||
    context.command like "*git push*" ||
    context.command like "*git pull*" ||
    context.command like "*git checkout*" ||
    context.command like "*git branch*" ||
    context.command like "*git merge*" ||
    context.command like "*git rebase*"
  )
};

//
// Policy 7: Deny access to credential files
//
@id("policy-7-deny-credential-files")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit"
  ],
  resource
)
when {
  context has filePath && (
    context.filePath like "*/.ssh/*" ||
    context.filePath like "*/.aws/*" ||
    context.filePath like "*/.config/openclaw/credentials*" ||
    context.filePath like "*.pem" ||
    context.filePath like "*.key" ||
    context.filePath like "*id_rsa" ||
    context.filePath like "*id_ed25519" ||
    context.filePath == ".env" ||
    context.filePath like "*/.env"
  )
};

//
// Policy 8: Example role-based policy (requires entity attributes)
// Uncomment when agent entities include role attribute
//
// @id("policy-8-admin-only-system-tools")
// permit(
//   principal,
//   action in [
//     OpenClaw::Action::"ToolExec::Process",
//     OpenClaw::Action::"ToolExec::ApplyPatch"
//   ],
//   resource
// )
// when {
//   principal has role && principal.role == "admin" ||
//   principal has securityLevel && principal.securityLevel == "high"
// };

//
// Policy 9: Time-based restrictions (example - requires clock in context)
// Uncomment when context includes timestamp
//
// @id("policy-9-business-hours-only")
// forbid(
//   principal,
//   action == OpenClaw::Action::"ToolExec::Bash",
//   resource
// )
// when {
//   // Deny destructive commands outside business hours
//   context has command && context has hour &&
//   (context.command like "*rm *" || context.command like "*delete*") &&
//   (context.hour < 9 || context.hour > 17)
// };

//
// Policy 10: Workspace-scoped permissions
//
@id("policy-10-workspace-scope")
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit"
  ],
  resource
)
when {
  context has filePath && (
    // Allow file operations only within workspace directory
    context.filePath like "/home/*" ||
    context.filePath like "/Users/*" ||
    context.filePath like "./*" ||
    !(context.filePath like "/*")
  )
};

//
// Demo Policies: Protect ~/openclaw-demo-protected directory
// These policies demonstrate Cedar authorization with a safe test directory
//

//
// Policy Demo-1: Deny reading credentials in protected directory
//
@id("policy-demo-1-deny-protected-credentials")
forbid(
  principal,
  action == OpenClaw::Action::"ToolExec::Read",
  resource
)
when {
  context has filePath &&
  context.filePath like "*/openclaw-demo-protected/credentials/*"
};

//
// Policy Demo-2: Deny writing to protected directory
//
@id("policy-demo-2-deny-protected-writes")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit"
  ],
  resource
)
when {
  context has filePath &&
  context.filePath like "*/openclaw-demo-protected/*"
};

//
// Policy Demo-3: Deny executing scripts in protected directory
//
@id("policy-demo-3-deny-protected-scripts")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Bash",
    OpenClaw::Action::"ToolExec::Exec"
  ],
  resource
)
when {
  context has command &&
  context.command like "*/openclaw-demo-protected/scripts/*"
};
