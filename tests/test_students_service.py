"""Student service: add/update/archive/restore/list/search/CSV-import.

Business rules only — the single testing seam. Routes stay thin; every
mutation is audited; archiving is a status transition, never a delete.
Route concerns live in ``test_students_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassNotFound, ClassService
from app.students.service import (
    StudentError,
    StudentImportError,
    StudentNotFound,
    StudentService,
)
from app.models import AuditLogEntry, Class, Student, StudentStatus, User, UserRoles

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


@pytest.fixture()
def admin(db, session) -> User:
    user = User(
        username="admin",
        name="Head Teacher",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture()
def grade1(classes, admin) -> Class:
    return classes.create_class(user=admin, name="Grade 1")


# ---------------------------------------------------------------------------
# add_student
# ---------------------------------------------------------------------------


def test_add_student_creates_an_active_student(students, grade1, session):
    student = students.add_student(
        user=None, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    row = session.query(Student).one()
    assert row.id == student.id
    assert row.class_id == grade1.id
    assert row.first_name == "Ada"
    assert row.last_name == "Lovelace"
    assert row.status == StudentStatus.ACTIVE
    assert row.full_name == "Ada Lovelace"


def test_add_student_trims_names(students, grade1, session):
    students.add_student(
        user=None, class_id=grade1.id, first_name="  Ada  ", last_name="  Lovelace  "
    )

    row = session.query(Student).one()
    assert row.first_name == "Ada"
    assert row.last_name == "Lovelace"


def test_add_student_requires_a_first_name(students, grade1):
    with pytest.raises(StudentError):
        students.add_student(user=None, class_id=grade1.id, first_name="", last_name="Lovelace")
    with pytest.raises(StudentError):
        students.add_student(user=None, class_id=grade1.id, first_name="   ", last_name="Lovelace")


def test_add_student_requires_a_last_name(students, grade1):
    with pytest.raises(StudentError):
        students.add_student(user=None, class_id=grade1.id, first_name="Ada", last_name="")


def test_add_student_missing_class_raises(students):
    with pytest.raises(ClassNotFound):
        students.add_student(user=None, class_id=999, first_name="Ada", last_name="Lovelace")


def test_add_student_is_audited(students, grade1, admin, session):
    students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_ADD).one()
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary
    assert "Grade 1" in entry.summary


# ---------------------------------------------------------------------------
# update_student
# ---------------------------------------------------------------------------


def test_update_student_changes_names(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.update_student(
        user=admin, student_id=student.id, first_name="Ada", last_name="King"
    )

    row = session.query(Student).one()
    assert row.first_name == "Ada"
    assert row.last_name == "King"


def test_update_student_requires_names(students, grade1, admin):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    with pytest.raises(StudentError):
        students.update_student(user=admin, student_id=student.id, first_name="", last_name="King")
    with pytest.raises(StudentError):
        students.update_student(user=admin, student_id=student.id, first_name="Ada", last_name="")


def test_update_student_missing_student_raises(students, grade1, admin):
    with pytest.raises(StudentNotFound):
        students.update_student(
            user=admin, student_id=999, first_name="Ada", last_name="King"
        )


def test_update_student_audits_old_and_new_names(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.update_student(
        user=admin, student_id=student.id, first_name="Ada", last_name="King"
    )

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_UPDATE).one()
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary
    assert "Ada King" in entry.summary


def test_update_student_without_change_writes_no_audit(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.update_student(
        user=admin, student_id=student.id, first_name="Ada", last_name="Lovelace"
    )

    assert session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_UPDATE).count() == 0


# ---------------------------------------------------------------------------
# archive_student / restore_student
# ---------------------------------------------------------------------------


def test_archive_student_marks_inactive_without_deleting(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.archive_student(user=admin, student_id=student.id)

    row = session.query(Student).one()
    assert row.status == StudentStatus.INACTIVE
    assert row.id == student.id  # still there, not deleted


def test_archive_student_is_audited(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.archive_student(user=admin, student_id=student.id)

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_ARCHIVE).one()
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary


def test_archive_already_inactive_student_is_a_no_op(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )
    students.archive_student(user=admin, student_id=student.id)

    students.archive_student(user=admin, student_id=student.id)

    assert session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_ARCHIVE).count() == 1


def test_archive_missing_student_raises(students, grade1, admin):
    with pytest.raises(StudentNotFound):
        students.archive_student(user=admin, student_id=999)


def test_restore_student_marks_active_again(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )
    students.archive_student(user=admin, student_id=student.id)

    students.restore_student(user=admin, student_id=student.id)

    assert session.query(Student).one().status == StudentStatus.ACTIVE


def test_restore_student_is_audited(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )
    students.archive_student(user=admin, student_id=student.id)

    students.restore_student(user=admin, student_id=student.id)

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_RESTORE).one()
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary


def test_restore_already_active_student_is_a_no_op(students, grade1, admin, session):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )

    students.restore_student(user=admin, student_id=student.id)

    assert session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_RESTORE).count() == 0


def test_restore_missing_student_raises(students, grade1, admin):
    with pytest.raises(StudentNotFound):
        students.restore_student(user=admin, student_id=999)


# ---------------------------------------------------------------------------
# list_students
# ---------------------------------------------------------------------------


def test_list_students_returns_the_classes_students_sorted_by_name(students, grade1, admin):
    students.add_student(user=admin, class_id=grade1.id, first_name="Zara", last_name="Zulu")
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")

    rows = students.list_students(grade1.id)

    assert [row.full_name for row in rows] == ["Ada Lovelace", "Zara Zulu"]


def test_list_students_only_includes_the_given_class(students, classes, grade1, admin):
    grade2 = classes.create_class(user=admin, name="Grade 2")
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")
    students.add_student(user=admin, class_id=grade2.id, first_name="Grace", last_name="Hopper")

    rows = students.list_students(grade1.id)

    assert [row.full_name for row in rows] == ["Ada Lovelace"]


def test_list_students_returns_empty_for_a_class_without_students(students, grade1):
    assert students.list_students(grade1.id) == []


def test_list_students_can_filter_by_status(students, grade1, admin):
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")
    archived = students.add_student(
        user=admin, class_id=grade1.id, first_name="Grace", last_name="Hopper"
    )
    students.archive_student(user=admin, student_id=archived.id)

    assert [row.full_name for row in students.list_students(grade1.id)] == [
        "Grace Hopper",
        "Ada Lovelace",
    ]
    assert [row.full_name for row in students.list_students(grade1.id, status=StudentStatus.ACTIVE)] == [
        "Ada Lovelace"
    ]
    assert [
        row.full_name for row in students.list_students(grade1.id, status=StudentStatus.INACTIVE)
    ] == ["Grace Hopper"]


def test_list_students_missing_class_raises(students):
    with pytest.raises(ClassNotFound):
        students.list_students(999)


# ---------------------------------------------------------------------------
# search_students
# ---------------------------------------------------------------------------


def test_search_students_matches_first_and_last_names_case_insensitively(
    students, classes, grade1, admin
):
    grade2 = classes.create_class(user=admin, name="Grade 2")
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")
    students.add_student(user=admin, class_id=grade2.id, first_name="Grace", last_name="Hopper")

    assert [s.full_name for s in students.search_students("ada")] == ["Ada Lovelace"]
    assert [s.full_name for s in students.search_students("HOPPER")] == ["Grace Hopper"]
    assert {s.full_name for s in students.search_students("a")} == {
        "Ada Lovelace",
        "Grace Hopper",
    }


def test_search_students_matches_the_full_name(students, classes, grade1, admin):
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")

    assert [s.full_name for s in students.search_students("ada lovelace")] == [
        "Ada Lovelace"
    ]


def test_search_students_returns_empty_for_no_matches(students, grade1, admin):
    students.add_student(user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace")

    assert students.search_students("nobody") == []


def test_search_students_orders_by_name_and_loads_the_class(students, classes, grade1, admin):
    grade2 = classes.create_class(user=admin, name="Grade 2")
    students.add_student(user=admin, class_id=grade1.id, first_name="Zara", last_name="Zulu")
    students.add_student(user=admin, class_id=grade2.id, first_name="Ada", last_name="Lovelace")

    rows = students.search_students("a")

    assert [row.full_name for row in rows] == ["Ada Lovelace", "Zara Zulu"]
    assert {row.school_class.name for row in rows} == {"Grade 1", "Grade 2"}


def test_search_students_includes_archived_students(students, grade1, admin):
    student = students.add_student(
        user=admin, class_id=grade1.id, first_name="Ada", last_name="Lovelace"
    )
    students.archive_student(user=admin, student_id=student.id)

    assert [s.full_name for s in students.search_students("ada")] == ["Ada Lovelace"]


# ---------------------------------------------------------------------------
# import_students_csv
# ---------------------------------------------------------------------------


def test_import_without_a_header_imports_every_row(students, grade1, session):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="Ada,Lovelace\nGrace,Hopper\n",
    )

    assert result.imported_count == 2
    assert result.skipped_count == 0
    assert [row.full_name for row in result.imported] == ["Ada Lovelace", "Grace Hopper"]
    names = {(s.first_name, s.last_name) for s in session.query(Student).all()}
    assert names == {("Ada", "Lovelace"), ("Grace", "Hopper")}


def test_import_recognises_a_header_row(students, grade1, session):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="first_name,last_name\nAda,Lovelace\n",
    )

    assert result.imported_count == 1
    assert result.skipped_count == 0
    assert result.imported[0].full_name == "Ada Lovelace"
    assert session.query(Student).count() == 1


def test_import_accepts_common_header_variants(students, grade1, session):
    content = "First Name,Surname\nAda,Lovelace\n"
    result = students.import_students_csv(
        user=None, class_id=grade1.id, content=content
    )

    assert result.imported_count == 1
    assert result.imported[0].full_name == "Ada Lovelace"


def test_import_trims_names(students, grade1):
    result = students.import_students_csv(
        user=None, class_id=grade1.id, content="  Ada  ,  Lovelace  \n"
    )

    assert result.imported[0].first_name == "Ada"
    assert result.imported[0].last_name == "Lovelace"


def test_import_skips_rows_missing_a_name_with_reasons(students, grade1, session):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="Ada,Lovelace\n,Lovelace\nAda,\nGrace,Hopper\n",
    )

    assert result.imported_count == 2
    assert result.skipped_count == 2
    assert [row.row_number for row in result.skipped] == [2, 3]
    assert all("first name" in row.reason for row in result.skipped if row.row_number == 2)
    assert all("last name" in row.reason for row in result.skipped if row.row_number == 3)
    assert session.query(Student).count() == 2


def test_import_skips_rows_duplicated_within_the_file(students, grade1, session):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="Ada,Lovelace\nAda,Lovelace\nGrace,Hopper\n",
    )

    assert result.imported_count == 2
    assert result.skipped_count == 1
    assert result.skipped[0].row_number == 2
    assert "duplicate" in result.skipped[0].reason
    assert session.query(Student).count() == 2


def test_import_reports_physical_line_numbers_ignoring_blank_lines(students, grade1):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="Ada,Lovelace\n\n,Lovelace\n\nGrace,Hopper\n",
    )

    assert [row.row_number for row in result.imported] == [1, 5]
    assert [row.row_number for row in result.skipped] == [3]


def test_import_does_not_confuse_a_student_named_first_last_with_a_header(students, grade1):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="First,Last\nAda,Lovelace\n",
    )

    assert result.imported_count == 2
    assert [row.full_name for row in result.imported] == ["First Last", "Ada Lovelace"]


def test_import_audit_records_the_filename_and_skips(students, grade1, admin, session):
    students.import_students_csv(
        user=admin,
        class_id=grade1.id,
        content="Ada,Lovelace\n,Lovelace\n",
        filename="register.csv",
    )

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.STUDENT_IMPORT).one()
    assert "register.csv" in entry.summary
    assert "1 row(s) skipped" in entry.summary


def test_import_ignores_blank_lines_silently(students, grade1, session):
    result = students.import_students_csv(
        user=None, class_id=grade1.id, content="Ada,Lovelace\n\n\nGrace,Hopper\n"
    )

    assert result.imported_count == 2
    assert result.skipped_count == 0


def test_import_uses_only_the_first_two_columns(students, grade1, session):
    result = students.import_students_csv(
        user=None,
        class_id=grade1.id,
        content="Ada,Lovelace,extra,stuff\n",
    )

    assert result.imported_count == 1
    assert result.imported[0].full_name == "Ada Lovelace"


def test_import_of_an_empty_file_raises(students, grade1):
    with pytest.raises(StudentImportError):
        students.import_students_csv(user=None, class_id=grade1.id, content="")
    with pytest.raises(StudentImportError):
        students.import_students_csv(user=None, class_id=grade1.id, content="\n\n")


def test_import_missing_class_raises(students):
    with pytest.raises(ClassNotFound):
        students.import_students_csv(user=None, class_id=999, content="Ada,Lovelace\n")


def test_import_is_audited_once_with_the_count(students, grade1, admin, session):
    students.import_students_csv(
        user=admin,
        class_id=grade1.id,
        content="Ada,Lovelace\n,Lovelace\nGrace,Hopper\n",
    )

    entries = (
        session.query(AuditLogEntry)
        .filter_by(action=AuditActions.STUDENT_IMPORT)
        .all()
    )
    assert len(entries) == 1
    assert entries[0].user_id == admin.id
    assert "2" in entries[0].summary
    assert "Grade 1" in entries[0].summary


def test_import_handles_a_utf8_bom(students, grade1, session):
    result = students.import_students_csv(
        user=None, class_id=grade1.id, content="\ufefffirst_name,last_name\nAda,Lovelace\n"
    )

    assert result.imported_count == 1
    assert result.imported[0].full_name == "Ada Lovelace"
