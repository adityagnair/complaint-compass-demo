from fastapi import APIRouter, HTTPException, Query

from backend.database import database
from backend.models.schemas import CustomerCreate

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post("")
def save_customer(customer: CustomerCreate):
    with database() as connection:
        connection.execute(
            """INSERT INTO customers (customer_id, country, state, age_group, student_status, income_bracket)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(customer_id) DO UPDATE SET
                 country = COALESCE(excluded.country, customers.country),
                 state = COALESCE(excluded.state, customers.state),
                 age_group = COALESCE(excluded.age_group, customers.age_group),
                 student_status = COALESCE(excluded.student_status, customers.student_status),
                 income_bracket = COALESCE(excluded.income_bracket, customers.income_bracket)""",
            (customer.customer_id, customer.country, customer.state, customer.age_group, customer.student_status, customer.income_bracket),
        )
        row = connection.execute("SELECT * FROM customers WHERE customer_id = ?", (customer.customer_id,)).fetchone()
    return dict(row)


@router.get("")
def list_customers(search: str | None = Query(default=None, max_length=200), limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    with database() as connection:
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            rows = connection.execute(
                """SELECT customers.*, COUNT(complaints.id) AS complaint_count
                   FROM customers LEFT JOIN complaints USING (customer_id)
                   WHERE customers.customer_id LIKE ? OR customers.country LIKE ? OR customers.state LIKE ?
                   GROUP BY customers.id ORDER BY customers.customer_id LIMIT ? OFFSET ?""",
                (pattern, pattern, pattern, limit, offset),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM customers WHERE customer_id LIKE ? OR country LIKE ? OR state LIKE ?", (pattern, pattern, pattern)).fetchone()[0]
        else:
            rows = connection.execute(
                """SELECT customers.*, COUNT(complaints.id) AS complaint_count
                   FROM customers LEFT JOIN complaints USING (customer_id)
                   GROUP BY customers.id ORDER BY customers.customer_id LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    return {"total": total, "items": [dict(row) for row in rows]}
