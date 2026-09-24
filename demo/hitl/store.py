"""In-memory pending-approval store. Timeouts are enforced here, not in Cedar."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any


class ApprovalStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def create(
        self,
        *,
        email_to: str,
        subject: str,
        body: str,
        request_hash: str,
        agent_id: str,
        tool_call_id: str,
        timeout_ms: int,
    ) -> dict[str, Any]:
        now = time.time()
        record = {
            "id": str(uuid.uuid4()),
            "to": email_to,
            "subject": subject,
            "body": body,
            "requestHash": request_hash,
            "agentId": agent_id,
            "toolCallId": tool_call_id,
            "status": "pending",
            "createdAt": now,
            "expiresAt": now + (timeout_ms / 1000.0),
            "event": threading.Event(),
        }
        with self._lock:
            self._items[record["id"]] = record
        return self._public(record)

    def get(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._items.get(approval_id)
            if record is None:
                return None
            self._expire_if_needed(record)
            return record

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            pending = []
            for record in self._items.values():
                self._expire_if_needed(record)
                if record["status"] == "pending":
                    pending.append(self._public(record))
            pending.sort(key=lambda item: item["createdAt"])
            return pending

    def wait(self, approval_id: str) -> dict[str, Any]:
        record = self.get(approval_id)
        if record is None:
            return {"id": approval_id, "status": "missing"}

        remaining = record["expiresAt"] - time.time()
        if remaining > 0 and record["status"] == "pending":
            record["event"].wait(timeout=remaining)

        record = self.get(approval_id)
        if record is None:
            return {"id": approval_id, "status": "missing"}

        if record["status"] == "approved":
            return {
                "id": record["id"],
                "status": "approved",
                "humanApproval": {
                    "verified": True,
                    "method": "webauthn",
                    "requestHash": record["requestHash"],
                },
            }

        with self._lock:
            if record["status"] == "pending":
                record["status"] = "expired"
        return {"id": record["id"], "status": "expired"}

    def approve(self, approval_id: str, request_hash: str) -> dict[str, Any]:
        with self._lock:
            record = self._items.get(approval_id)
            if record is None:
                raise KeyError("unknown approval")
            self._expire_if_needed(record)
            if record["status"] != "pending":
                raise ValueError("approval is no longer pending")
            if record["requestHash"] != request_hash:
                raise ValueError("request hash mismatch")
            record["status"] = "approved"
            record["event"].set()
            return self._public(record)

    def _expire_if_needed(self, record: dict[str, Any]) -> None:
        if record["status"] == "pending" and time.time() >= record["expiresAt"]:
            record["status"] = "expired"
            record["event"].set()

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "to": record["to"],
            "subject": record["subject"],
            "body": record["body"],
            "requestHash": record["requestHash"],
            "agentId": record["agentId"],
            "toolCallId": record["toolCallId"],
            "status": record["status"],
            "createdAt": record["createdAt"],
            "expiresAt": record["expiresAt"],
        }
