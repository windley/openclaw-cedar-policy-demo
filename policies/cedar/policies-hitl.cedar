// Cedar HITL policies for simulated email send.
//
// Sending email is allowed only after the PEP injects a verified WebAuthn
// approval whose requestHash matches this call. Timeout and replay checks
// live in the PEP (Cedar has no now()). Drafting and reads are unaffected.

@id("hitl-1-allow-send-with-approval")
permit(
  principal,
  action == OpenClaw::Action::"ToolExec::SendEmail",
  resource
)
when {
  context has humanApproval &&
  context.humanApproval.verified == true &&
  context.humanApproval.method == "webauthn" &&
  context has requestHash &&
  context.humanApproval.requestHash == context.requestHash
};

@id("hitl-2-forbid-send-without-approval")
forbid(
  principal,
  action == OpenClaw::Action::"ToolExec::SendEmail",
  resource
)
when {
  !(
    context has humanApproval &&
    context.humanApproval.verified == true &&
    context.humanApproval.method == "webauthn" &&
    context has requestHash &&
    context.humanApproval.requestHash == context.requestHash
  )
};
