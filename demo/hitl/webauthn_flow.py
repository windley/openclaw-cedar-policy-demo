"""Yubikey (WebAuthn) registration and request-bound authentication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

RP_ID = "localhost"
RP_NAME = "OpenClaw HITL Approver"
ORIGIN = "http://localhost:8180"
USER_ID = b"openclaw-approver"
USER_NAME = "approver"


class WebAuthnManager:
    def __init__(self, credentials_path: Path) -> None:
        self.credentials_path = credentials_path
        self._registration_challenge: bytes | None = None
        self._credentials = self._load()

    def status(self) -> dict[str, Any]:
        return {"registered": len(self._credentials) > 0}

    def registration_options(self) -> dict[str, Any]:
        options = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=USER_ID,
            user_name=USER_NAME,
            user_display_name="OpenClaw Approver",
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        self._registration_challenge = options.challenge
        return json.loads(options_to_json(options))

    def verify_registration(self, credential: str | dict[str, Any]) -> dict[str, Any]:
        if self._registration_challenge is None:
            raise ValueError("no registration in progress")
        payload = credential if isinstance(credential, str) else json.dumps(credential)
        verification = verify_registration_response(
            credential=payload,
            expected_challenge=self._registration_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=True,
        )
        self._registration_challenge = None
        record = {
            "id": bytes_to_base64url(verification.credential_id),
            "publicKey": bytes_to_base64url(verification.credential_public_key),
            "signCount": verification.sign_count,
        }
        self._credentials = [record]
        self._save()
        return {"verified": True, "credentialId": record["id"]}

    def authentication_options(self, request_hash_hex: str) -> dict[str, Any]:
        if not self._credentials:
            raise ValueError("no Yubikey registered")
        challenge = bytes.fromhex(request_hash_hex)
        options = generate_authentication_options(
            rp_id=RP_ID,
            challenge=challenge,
            timeout=120000,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item["id"]))
                for item in self._credentials
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return json.loads(options_to_json(options))

    def verify_authentication(
        self,
        credential: str | dict[str, Any],
        request_hash_hex: str,
    ) -> dict[str, Any]:
        if not self._credentials:
            raise ValueError("no Yubikey registered")
        payload = credential if isinstance(credential, str) else json.dumps(credential)
        raw_id = _credential_id(payload)
        stored = next((item for item in self._credentials if item["id"] == raw_id), None)
        if stored is None:
            raise ValueError("unknown credential")
        verification = verify_authentication_response(
            credential=payload,
            expected_challenge=bytes.fromhex(request_hash_hex),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64url_to_bytes(stored["publicKey"]),
            credential_current_sign_count=stored["signCount"],
            require_user_verification=True,
        )
        stored["signCount"] = verification.new_sign_count
        self._save()
        return {"verified": True, "credentialId": stored["id"]}

    def _load(self) -> list[dict[str, Any]]:
        if not self.credentials_path.exists():
            return []
        data = json.loads(self.credentials_path.read_text())
        return list(data.get("credentials") or [])

    def _save(self) -> None:
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        self.credentials_path.write_text(
            json.dumps({"credentials": self._credentials}, indent=2) + "\n"
        )


def _credential_id(payload: str) -> str:
    parsed = json.loads(payload)
    return parsed.get("rawId") or parsed.get("id") or ""
