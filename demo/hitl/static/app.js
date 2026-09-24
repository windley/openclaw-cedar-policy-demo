function b64urlToBuf(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function bufToB64url(buf) {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodePublicKeyOptions(options) {
  const decoded = { ...options, challenge: b64urlToBuf(options.challenge) };
  if (options.user?.id) {
    decoded.user = { ...options.user, id: b64urlToBuf(options.user.id) };
  }
  if (Array.isArray(options.excludeCredentials)) {
    decoded.excludeCredentials = options.excludeCredentials.map((item) => ({
      ...item,
      id: b64urlToBuf(item.id),
    }));
  }
  if (Array.isArray(options.allowCredentials)) {
    decoded.allowCredentials = options.allowCredentials.map((item) => ({
      ...item,
      id: b64urlToBuf(item.id),
    }));
  }
  return decoded;
}

function serializeCredential(credential) {
  const response = credential.response;
  const payload = {
    id: credential.id,
    rawId: bufToB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufToB64url(response.clientDataJSON),
    },
  };
  if (response.attestationObject) {
    payload.response.attestationObject = bufToB64url(response.attestationObject);
  }
  if (response.authenticatorData) {
    payload.response.authenticatorData = bufToB64url(response.authenticatorData);
  }
  if (response.signature) {
    payload.response.signature = bufToB64url(response.signature);
  }
  if (response.userHandle) {
    payload.response.userHandle = bufToB64url(response.userHandle);
  }
  return payload;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

function remainingLabel(expiresAt) {
  const seconds = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  return `${seconds}s left`;
}

const registerStatus = document.getElementById("register-status");
const registerBtn = document.getElementById("register-btn");
const pendingEmpty = document.getElementById("pending-empty");
const pendingList = document.getElementById("pending-list");
const sentEmpty = document.getElementById("sent-empty");
const sentList = document.getElementById("sent-list");

let registered = false;

async function refreshStatus() {
  const status = await fetchJson("/webauthn/status");
  registered = Boolean(status.registered);
  registerStatus.textContent = registered
    ? "A Yubikey is registered on this demo."
    : "No Yubikey registered yet.";
  registerBtn.textContent = registered ? "Register a different Yubikey" : "Register Yubikey";
}

registerBtn.addEventListener("click", async () => {
  registerBtn.disabled = true;
  try {
    const options = decodePublicKeyOptions(await fetchJson("/webauthn/register/options"));
    const credential = await navigator.credentials.create({ publicKey: options });
    await fetchJson("/webauthn/register/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeCredential(credential)),
    });
    await refreshStatus();
  } catch (err) {
    registerStatus.textContent = err.message;
    registerStatus.classList.add("error");
  } finally {
    registerBtn.disabled = false;
  }
});

async function approve(approval) {
  const options = decodePublicKeyOptions(
    await fetchJson(`/webauthn/authenticate/options?approvalId=${encodeURIComponent(approval.id)}`),
  );
  const credential = await navigator.credentials.get({ publicKey: options });
  await fetchJson("/webauthn/authenticate/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      approvalId: approval.id,
      credential: serializeCredential(credential),
    }),
  });
}

function renderPending(items) {
  pendingList.innerHTML = "";
  pendingEmpty.style.display = items.length ? "none" : "block";
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <h3>${escapeHtml(item.subject || "(no subject)")}</h3>
      <p class="meta">To ${escapeHtml(item.to)} · ${remainingLabel(item.expiresAt)}</p>
      <pre>${escapeHtml(item.body || "")}</pre>
    `;
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = "Approve with Yubikey";
    button.disabled = !registered;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await approve(item);
        await refreshLists();
      } catch (err) {
        const error = document.createElement("p");
        error.className = "error";
        error.textContent = err.message;
        card.appendChild(error);
        button.disabled = !registered;
      }
    });
    card.appendChild(button);
    pendingList.appendChild(card);
  }
}

function renderSent(items) {
  sentList.innerHTML = "";
  sentEmpty.style.display = items.length ? "none" : "block";
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <h3>${escapeHtml(item.subject || item.filename)}</h3>
      <p class="meta">${escapeHtml(item.filename)}${item.to ? ` · To ${escapeHtml(item.to)}` : ""}</p>
      <pre>${escapeHtml(item.body || "")}</pre>
    `;
    sentList.appendChild(card);
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function refreshLists() {
  const [pending, sent] = await Promise.all([
    fetchJson("/approvals"),
    fetchJson("/mailbox"),
  ]);
  renderPending(pending.items || []);
  renderSent(sent.items || []);
}

refreshStatus()
  .then(refreshLists)
  .catch((err) => {
    registerStatus.textContent = err.message;
    registerStatus.classList.add("error");
  });

setInterval(() => {
  refreshLists().catch(() => {});
}, 2000);
