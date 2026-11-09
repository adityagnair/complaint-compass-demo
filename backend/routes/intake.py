import hashlib
import hmac
import json
import os
import re
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, status

from backend.models.schemas import ComplaintCreate, CustomerFields
from backend.routes.complaints import insert_complaint
from backend.services.complaints import parse_timestamp

router = APIRouter(prefix="/api/intake", tags=["channel intake"])
CHANNELS = {"email", "voice", "chatbot", "social"}
MAX_PAYLOAD_BYTES = 64 * 1024


def _first(data: dict, *keys: str):
    folded = {str(key).casefold().replace("-", "_"): value for key, value in data.items()}
    for key in keys:
        value = data.get(key)
        if value is None:
            value = folded.get(key.casefold().replace("-", "_"))
        if value is not None and value != "":
            return value
    return None


def _stable_id(channel: str, source_id, text: str, timestamp: datetime, sender) -> str:
    if source_id:
        external_id = str(source_id).strip()
        if len(external_id) <= 80:
            return f"{channel}-{external_id}"
        return f"{channel}-{hashlib.sha256(external_id.encode()).hexdigest()}"
    identity = "\x1f".join((channel, str(sender or ""), timestamp.isoformat(), text))
    return f"{channel}-{hashlib.sha256(identity.encode()).hexdigest()}"


def _alias_key(channel: str, sender) -> str | None:
    if not sender:
        return None
    value = str(sender).strip().casefold()
    if "@" in value:
        value = value.replace(" ", "")
    elif channel == "voice":
        value = re.sub(r"[^+\d]", "", value)
    else:
        value = re.sub(r"\s+", "", value)
    if not value:
        return None
    alias = f"{channel}:{value}"
    return alias if len(alias) <= 220 else f"{channel}:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _normalize(channel: str, payload: dict) -> ComplaintCreate:
    nested = payload.get("data")
    if isinstance(nested, dict):
        payload = {**payload, **nested}
    nested_message = payload.get("message")
    if isinstance(nested_message, dict):
        payload = {**payload, **nested_message}

    customer_identity = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    canonical_id = _first(payload, "canonical_customer_id", "identity_id", "crm_customer_id", "customer_id")
    if not canonical_id:
        canonical_id = _first(customer_identity, "canonical_customer_id", "identity_id", "crm_customer_id", "customer_id")
    if channel == "email":
        raw_text = _first(payload, "complaint_text", "text", "body", "body_plain", "body-plain", "text_body", "textbody", "snippet")
        subject = _first(payload, "subject")
        sender = _first(payload, "from", "sender", "email")
        source_id = _first(payload, "event_id", "message_id", "messageid", "Message-Id", "id")
        text = f"{subject}: {raw_text}" if subject and raw_text else raw_text
    elif channel == "voice":
        text = _first(payload, "transcript", "transcription", "speech_result", "SpeechResult", "text", "complaint_text")
        sender = _first(payload, "caller", "caller_id", "from", "phone_number")
        source_id = _first(payload, "event_id", "call_sid", "CallSid", "recording_sid", "id")
    elif channel == "chatbot":
        text = _first(payload, "complaint_text", "text", "content", "message_text", "message")
        sender = _first(payload, "user_id", "user", "from", "sender")
        source_id = _first(payload, "event_id", "message_id", "id")
    else:
        text = _first(payload, "complaint_text", "text", "content", "message_text", "message")
        sender = _first(payload, "author_id", "user_id", "from", "sender")
        source_id = _first(payload, "event_id", "message_id", "post_id", "id")

    if isinstance(text, dict) or not isinstance(text, str) or len(text.strip()) < 3:
        raise HTTPException(status_code=422, detail=f"A complaint message or transcript is required for {channel} intake.")
    if len(text) > 10_000:
        raise HTTPException(status_code=422, detail="Complaint text must be 10,000 characters or fewer.")

    if isinstance(sender, dict):
        sender = _first(sender, "email", "phone_number", "id", "username", "handle")
    alias = _alias_key(channel, sender)
    resolved_customer_id = canonical_id
    if not resolved_customer_id and alias:
        from backend.database import database

        with database() as connection:
            match = connection.execute("SELECT customer_id FROM customer_aliases WHERE alias_value = ?", (alias,)).fetchone()
        resolved_customer_id = match["customer_id"] if match else sender

    try:
        timestamp = parse_timestamp(_first(payload, "timestamp", "received_at", "created_at", "date"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    customer_payload = payload.get("customer")
    customer_payload = customer_payload if isinstance(customer_payload, dict) else payload
    try:
        customer = CustomerFields(
            country=customer_payload.get("country"),
            state=customer_payload.get("state"),
            age_group=customer_payload.get("age_group"),
            student_status=customer_payload.get("student_status"),
            income_bracket=customer_payload.get("income_bracket"),
        )
        complaint_values = dict(
            complaint_id=_stable_id(channel, source_id, text.strip(), timestamp, sender),
            customer_id=str(resolved_customer_id).strip()[:100] if resolved_customer_id else None,
            complaint_text=text,
            channel=channel,
            timestamp=timestamp,
            customer=customer,
            customer_aliases=[alias] if alias else [],
            customer_identity_verified=bool(canonical_id),
        )
        if payload.get("severity") is not None:
            complaint_values["severity"] = int(payload["severity"])
        return ComplaintCreate(**complaint_values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid intake payload: {exc}") from exc


def _authorize(authorization: str | None, x_intake_token: str | None) -> None:
    expected_token = os.getenv("INTAKE_WEBHOOK_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="Channel intake is not configured.")
    supplied_token = x_intake_token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied_token = authorization[7:].strip()
    if not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid intake credentials.")


async def _read_payload(request: Request) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Intake payload exceeds 64 KB.")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Send a JSON payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The JSON payload must be an object.")
    return payload


def _ingest(channel: str, payload: dict) -> dict:
    channel = channel.lower()
    if channel not in CHANNELS:
        raise HTTPException(status_code=422, detail="Channel must be email, voice, chatbot, or social.")
    complaint = _normalize(channel, payload)
    from backend.database import database

    with database() as connection:
        inserted = insert_complaint(connection, complaint)
    return {
        "status": "accepted" if inserted else "duplicate",
        "complaint_id": complaint.complaint_id,
        "channel": channel,
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_any_complaint(
    request: Request,
    authorization: str | None = Header(default=None),
    x_intake_token: str | None = Header(default=None),
):
    _authorize(authorization, x_intake_token)
    payload = await _read_payload(request)
    channel = payload.pop("channel", "")
    if not isinstance(channel, str):
        raise HTTPException(status_code=422, detail="Channel must be email, voice, chatbot, or social.")
    return _ingest(channel, payload)


@router.post("/{channel}", status_code=status.HTTP_202_ACCEPTED)
async def receive_complaint(
    channel: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_intake_token: str | None = Header(default=None),
):
    _authorize(authorization, x_intake_token)
    return _ingest(channel, await _read_payload(request))
