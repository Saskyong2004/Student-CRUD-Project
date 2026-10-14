
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator


DATABASE = "students.db"

@contextmanager
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                course TEXT,
                address TEXT,
                enrollment_date TEXT
            )
        """)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Student Management API",
    description="Student CRUD application for the EWB internship.",
    version="1.0.0",
    lifespan=lifespan,
)


class StudentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    course: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=250)
    enrollment_date: date | None = None

    @model_validator(mode="after")
    def validate_contact(self):
        if not self.email and not self.phone:
            raise ValueError("Provide an email address or phone number.")

        if self.email and (
            "@" not in self.email
            or "." not in self.email.rsplit("@", 1)[-1]
        ):
            raise ValueError("Enter a valid email address.")

        return self


class StudentPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=100)
    date_of_birth: date | None = None
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    course: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=250)
    enrollment_date: date | None = None


def find_student(student_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_id = ?",
            (student_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")

    return dict(row)


@app.get("/")
def home():
    return {"message": "Student Management API is running"}


@app.post("/students", status_code=201)
def create_student(student: StudentCreate):
    data = student.model_dump()

    data["date_of_birth"] = student.date_of_birth.isoformat()
    data["enrollment_date"] = (
        student.enrollment_date.isoformat()
        if student.enrollment_date else None
    )

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO students
            (name, date_of_birth, email, phone, course, address,
             enrollment_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["name"], data["date_of_birth"], data["email"],
            data["phone"], data["course"], data["address"],
            data["enrollment_date"],
        ))
        student_id = cursor.lastrowid

    return find_student(student_id)


@app.get("/students")
def list_students(
    name: str | None = None,
    course: str | None = None,
    born_after: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    sql = "SELECT * FROM students WHERE 1=1"
    params = []

    if name:
        sql += " AND name LIKE ?"
        params.append(f"%{name}%")

    if course:
        sql += " AND course LIKE ?"
        params.append(f"%{course}%")

    if born_after:
        sql += " AND date_of_birth > ?"
        params.append(born_after.isoformat())

    sql += " ORDER BY student_id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


@app.get("/students/{student_id}")
def get_student(student_id: int):
    return find_student(student_id)


@app.put("/students/{student_id}")
def replace_student(student_id: int, student: StudentCreate):
    find_student(student_id)
    data = student.model_dump()

    data["date_of_birth"] = student.date_of_birth.isoformat()
    data["enrollment_date"] = (
        student.enrollment_date.isoformat()
        if student.enrollment_date else None
    )

    with get_connection() as conn:
        conn.execute("""
            UPDATE students
            SET name=?, date_of_birth=?, email=?, phone=?,
                course=?, address=?, enrollment_date=?
            WHERE student_id=?
        """, (
            data["name"], data["date_of_birth"], data["email"],
            data["phone"], data["course"], data["address"],
            data["enrollment_date"], student_id,
        ))

    return find_student(student_id)


@app.patch("/students/{student_id}")
def update_student(student_id: int, changes: StudentPatch):
    existing = find_student(student_id)
    updates = changes.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    merged = {**existing, **updates}

    # Revalidate the resulting contact information and field constraints.
    contact = StudentCreate.model_validate({
        key: merged[key]
        for key in StudentCreate.model_fields
    })

    data = contact.model_dump()
    data["date_of_birth"] = contact.date_of_birth.isoformat()
    data["enrollment_date"] = (
        contact.enrollment_date.isoformat()
        if contact.enrollment_date else None
    )

    with get_connection() as conn:
        conn.execute("""
            UPDATE students
            SET name=?, date_of_birth=?, email=?, phone=?,
                course=?, address=?, enrollment_date=?
            WHERE student_id=?
        """, (
            data["name"], data["date_of_birth"], data["email"],
            data["phone"], data["course"], data["address"],
            data["enrollment_date"], student_id,
        ))

    return find_student(student_id)


@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    find_student(student_id)

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM students WHERE student_id = ?",
            (student_id,),
        )

    return {"message": "Student deleted successfully",
            "student_id": student_id}
