"""Ephemeral single-user device pairing for the controlled local prototype."""
from datetime import UTC, datetime
import hashlib
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class DeviceSessions:
    def __init__(self, owner, clock=time.time):
        self.owner = owner
        self.clock = clock
        self.codes = {}
        self.sessions = {}
        self.lock = threading.Lock()

    @staticmethod
    def key(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def prune(self):
        now = self.clock()
        self.codes = {k:v for k,v in self.codes.items() if v > now}
        self.sessions = {k:v for k,v in self.sessions.items() if v > now}

    def issue(self):
        with self.lock:
            self.prune()
            if len(self.codes) >= 20:
                raise HTTPException(429, "Too many pending device pairings")
            code = secrets.token_urlsafe(18)
            expires = self.clock() + 120
            self.codes[self.key(code)] = expires
            return {"pairing_code":code, "expires_at":datetime.fromtimestamp(expires, UTC).isoformat()}

    def exchange(self, code):
        with self.lock:
            self.prune()
            if self.codes.pop(self.key(code), None) is None:
                raise HTTPException(401, detail={"code":"pairing_invalid_or_expired", "message":"配对码无效或已过期，请在电脑上重新生成"})
            token = secrets.token_urlsafe(32)
            expires = self.clock() + 3600
            self.sessions[self.key(token)] = expires
            return {"access_token":token, "token_type":"bearer", "expires_at":datetime.fromtimestamp(expires, UTC).isoformat()}

    def authenticate(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return None
        with self.lock:
            self.prune()
            return self.owner if self.key(authorization[7:]) in self.sessions else None

    def revoke(self, authorization):
        with self.lock:
            self.sessions.pop(self.key((authorization or "")[7:]), None)


class PairingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_code: str = Field(min_length=16, max_length=100)


def create_device_router(sessions, server_authorized):
    router = APIRouter(prefix="/api/v1", tags=["local-device-access"])

    @router.post("/device-pairing")
    def issue(request: Request):
        if not server_authorized(request):
            raise HTTPException(403, "Host authorization required")
        return sessions.issue()

    @router.post("/device-sessions")
    def pair(payload: PairingInput):
        return sessions.exchange(payload.pairing_code)

    @router.delete("/device-sessions/current", status_code=204)
    def revoke(request: Request):
        sessions.revoke(request.headers.get("authorization"))

    return router
