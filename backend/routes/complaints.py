from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from backend.database import database
from backend.models.schemas import ComplaintCreate
from backend.services.complaints import parse_csv

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def upsert_customer(connection, customer_id: str, fields) -> None:
    connection.execute(
        """INSERT INTO customers (customer_id, country, state, age_group, student_status, income_bracket)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(customer_id) DO UPDATE SET
             country = COALESCE(excluded.country, customers.country),
             state = COALESCE(excluded.state, customers.state),
             age_group = COALESCE(excluded.age_group, customers.age_group),
             student_status = COALESCE(excluded.student_status, customers.student_status),
             income_bracket = COALESCE(excluded.income_bracket, customers.income_bracket)""",
        (customer_id, fields.country, fields.state, fields.age_group, fields.student_status, fields.income_bracket),
    )


def insert_complaint(connection, complaint: ComplaintCreate) -> bool:
    if complaint.customer_id:
        upsert_customer(connection, complaint.customer_id, complaint.customer)
    result = connection.execute(
        """INSERT INTO complaints (complaint_id, customer_id, complaint_text, channel, submitted_at, severity)
           VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(complaint_id) DO NOTHING""",
        (
            complaint.complaint_id,
            complaint.customer_id,
            complaint.complaint_text,
            complaint.channel,
            complaint.timestamp.isoformat(),
            complaint.severity,
        ),
    )
    return result.rowcount > 0


@router.post("", status_code=status.HTTP_201_CREATED)
def create_complaint(complaint: ComplaintCreate):
    with database() as connection:
        inserted = insert_complaint(connection, complaint)
    if not inserted:
        raise HTTPException(status_code=409, detail="complaint_id already exists")
    return {"complaint_id": complaint.complaint_id, "status": "created"}


@router.post("/upload")
async def upload_complaints(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please choose a .csv file")
    content = await file.read(10 * 1024 * 1024 + 1)
    try:
        valid_rows, errors = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    added = 0
    with database() as connection:
        for line_number, complaint in valid_rows:
            if insert_complaint(connection, complaint):
                added += 1
            else:
                errors.append({"row": str(line_number), "error": f"complaint_id {complaint.complaint_id} already exists"})
    return {"filename": file.filename, "added": added, "skipped": len(errors), "errors": errors}


@router.get("")
def list_complaints(
    search: str | None = Query(default=None, max_length=200),
    channel: str | None = Query(default=None, max_length=30),
    severity: int | None = Query(default=None, ge=1, le=5),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    conditions: list[str] = []
    values: list[object] = []
    if search and search.strip():
        conditions.append("(complaints.complaint_text LIKE ? OR complaints.complaint_id LIKE ? OR complaints.customer_id LIKE ?)")
        pattern = f"%{search.strip()}%"
        values.extend((pattern, pattern, pattern))
    if channel:
        conditions.append("complaints.channel = ?")
        values.append(channel.lower())
    if severity is not None:
        conditions.append("complaints.severity = ?")
        values.append(severity)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with database() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM complaints {where}", values).fetchone()[0]
        rows = connection.execute(
            f"""SELECT complaints.*, customers.country, customers.state, customers.age_group,
                       customers.student_status, customers.income_bracket, issue_clusters.label AS issue_label
                FROM complaints LEFT JOIN customers USING (customer_id)
                LEFT JOIN issue_clusters ON issue_clusters.cluster_id = complaints.issue_cluster_id
                {where} ORDER BY complaints.submitted_at DESC, complaints.id DESC LIMIT ? OFFSET ?""",
            [*values, limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(row) for row in rows]}


@router.get("/{complaint_id}")
def get_complaint(complaint_id: str):
    with database() as connection:
        row = connection.execute(
            """SELECT complaints.*, customers.country, customers.state, customers.age_group,
                      customers.student_status, customers.income_bracket, issue_clusters.label AS issue_label
               FROM complaints LEFT JOIN customers USING (customer_id)
               LEFT JOIN issue_clusters ON issue_clusters.cluster_id = complaints.issue_cluster_id
               WHERE complaints.complaint_id = ?""",
            (complaint_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return dict(row)
