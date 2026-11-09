import csv
import io
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.models.schemas import ComplaintCreate, CustomerFields

HEADER_ALIASES = {
    "complaint_id": {"complaint_id", "complaintid", "id", "ticket_id", "ticketid"},
    "customer_id": {"customer_id", "customerid", "user_id", "userid"},
    "complaint_text": {"complaint_text", "complaint", "description", "text", "message"},
    "channel": {"channel", "source", "complaint_source"},
    "timestamp": {"timestamp", "date", "created_at", "submitted_at", "time"},
    "severity": {"severity", "priority", "urgency"},
    "country": {"country"},
    "state": {"state", "region", "province"},
    "age_group": {"age_group", "age", "age_range"},
    "student_status": {"student_status", "is_student", "student"},
    "income_bracket": {"income_bracket", "income", "income_range"},
}
CHANNELS = {
    "email": "email", "e-mail": "email", "voice": "voice", "call": "voice", "phone": "voice",
    "chat": "chatbot", "chatbot": "chatbot", "social": "social", "social media": "social",
    "web": "web", "website": "web",
}
SEVERITY_LABELS = {"low": 1, "minor": 1, "medium": 3, "normal": 3, "high": 4, "critical": 5, "urgent": 5}


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def canonicalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {normalize_header(key): (value or "").strip() for key, value in row.items() if key}
    values: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                values[canonical] = normalized[alias]
                break
    return values


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("timestamp must be ISO format or a recognizable date")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def row_to_complaint(row: dict[str, str], line_number: int) -> ComplaintCreate:
    values = canonicalize_row(row)
    if not values.get("complaint_id"):
        raise ValueError("complaint_id (or ID) is required")
    if not values.get("complaint_text"):
        raise ValueError("complaint_text (or Complaint/description) is required")
    channel_input = values.get("channel", "other").strip().lower()
    channel = CHANNELS.get(channel_input, "other")
    severity_input = values.get("severity", "").strip().lower()
    if not severity_input:
        severity = None
    elif severity_input.isdigit():
        severity = int(severity_input)
    elif severity_input in SEVERITY_LABELS:
        severity = SEVERITY_LABELS[severity_input]
    else:
        raise ValueError("severity must be a number from 1 to 5 or a known severity label")
    customer = CustomerFields(
        country=values.get("country") or None,
        state=values.get("state") or None,
        age_group=values.get("age_group") or None,
        student_status=values.get("student_status") or None,
        income_bracket=values.get("income_bracket") or None,
    )
    try:
        complaint_values = dict(
            complaint_id=values["complaint_id"],
            customer_id=values.get("customer_id") or None,
            complaint_text=values["complaint_text"],
            channel=channel,
            timestamp=parse_timestamp(values.get("timestamp")),
            customer=customer,
        )
        if severity is not None:
            complaint_values["severity"] = severity
        return ComplaintCreate(**complaint_values)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise ValueError(details) from exc


def parse_csv(content: bytes) -> tuple[list[tuple[int, ComplaintCreate]], list[dict[str, str]]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("CSV exceeds the 10 MB upload limit")
    try:
        dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(decoded, newline=""), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV is empty or has no header row")
    headers = {normalize_header(header) for header in reader.fieldnames if header}
    if not headers.intersection(HEADER_ALIASES["complaint_id"]) or not headers.intersection(HEADER_ALIASES["complaint_text"]):
        raise ValueError("CSV must include complaint_id (or ID) and complaint_text (or Complaint/description) columns")
    valid: list[tuple[int, ComplaintCreate]] = []
    errors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        try:
            complaint = row_to_complaint(row, line_number)
            if complaint.complaint_id in seen_ids:
                raise ValueError("duplicate complaint_id in this file")
            seen_ids.add(complaint.complaint_id)
            valid.append((line_number, complaint))
        except (ValueError, ValidationError) as exc:
            errors.append({"row": str(line_number), "error": str(exc)})
    return valid, errors
