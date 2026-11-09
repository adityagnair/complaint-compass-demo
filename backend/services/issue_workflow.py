import hashlib
import re
import unicodedata


def issue_key(label: str) -> str:
    normalized = unicodedata.normalize("NFKC", label).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def workflow_for_label(connection, label: str) -> dict:
    key = issue_key(label)
    row = connection.execute("SELECT status, owner, notes, updated_at FROM issue_work_items WHERE issue_key = ?", (key,)).fetchone()
    return {
        "issue_key": key,
        "status": row["status"] if row else "open",
        "owner": row["owner"] if row else None,
        "notes": row["notes"] if row else "",
        "updated_at": row["updated_at"] if row else None,
    }
