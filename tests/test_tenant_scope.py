"""Tenant scope: campus-scoped class/student service behavior (multi-school 03).

Service-level tests with a seeded scope: the request scope resolves from the
acting user (``RequestScope.for_user``) and filters reads and stamps writes on
class and student operations. Two Campuses of one School, an Admin bound to
each, and a bound Superadmin; legacy NULL-campus rows stay visible to every
scope. Route concerns live in ``test_classes_routes.py`` /
``test_students_routes.py``.
"""

import pytest

from app.audit.service import AuditService
from app.classes.service import ClassError, ClassNotFound, ClassService
from app.models import (
    Campus,
    Class,
    FeeTemplate,
    School,
    Student,
    StudentAmountChange,
    User,
    UserRoles,
)
from app.students.service import StudentNotFound, StudentService, TemplateNotFound
from app.tenants.scope import RequestScope, scope_context

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


def seed_tenant_world(session):
    """One School, two Campuses, an Admin bound to each, and a Superadmin."""
    school = School(name="Sunrise Academy")
    session.add(school)
    session.flush()
    campus_a = Campus(school_id=school.id, name="Campus A")
    campus_b = Campus(school_id=school.id, name="Campus B")
    session.add_all([campus_a, campus_b])
    session.flush()
    admin_a = User(
        username="admin_a",
        name="Admin A",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
        school_id=school.id,
        campus_id=campus_a.id,
    )
    admin_b = User(
        username="admin_b",
        name="Admin B",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
        school_id=school.id,
        campus_id=campus_b.id,
    )
    superadmin = User(
        username="super",
        name="Super",
        password_hash=PASSWORD,
        role=UserRoles.SUPERADMIN,
        school_id=school.id,
    )
    session.add_all([admin_a, admin_b, superadmin])
    session.commit()
    return school, campus_a, campus_b, admin_a, admin_b, superadmin


def seed_classes_students(session, campus_a, campus_b):
    """One class + student per campus, plus a legacy NULL-campus pair."""
    cls_a = Class(name="Grade A", campus_id=campus_a.id)
    cls_b = Class(name="Grade B", campus_id=campus_b.id)
    legacy_cls = Class(name="Legacy")
    session.add_all([cls_a, cls_b, legacy_cls])
    session.flush()
    student_a = Student(
        class_id=cls_a.id, campus_id=campus_a.id, first_name="Ada", last_name="Lovelace"
    )
    student_b = Student(
        class_id=cls_b.id, campus_id=campus_b.id, first_name="Grace", last_name="Hopper"
    )
    legacy_student = Student(class_id=legacy_cls.id, first_name="Alan", last_name="Turing")
    session.add_all([student_a, student_b, legacy_student])
    session.commit()
    return cls_a, cls_b, legacy_cls, student_a, student_b, legacy_student


# ---------------------------------------------------------------------------
# Reads: lists and search
# ---------------------------------------------------------------------------


def test_campus_admin_lists_only_own_campus_and_legacy_classes(classes, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, cls_b, legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        rows = classes.list_class_summaries()

    assert {row.cls.id for row in rows} == {cls_a.id, legacy_cls.id}


def test_campus_admin_searches_only_own_campus_and_legacy_students(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, _cls_b, _legacy_cls, student_a, student_b, legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        rows = students.search_students("")

    assert {row.id for row in rows} == {student_a.id, legacy_student.id}


def test_campus_admin_list_students_only_sees_own_campus(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, _cls_b, _legacy_cls, student_a, student_b, legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        rows = students.list_students(cls_a.id)

    assert {row.id for row in rows} == {student_a.id}


def test_campus_admin_student_counts_ignore_other_campus(classes, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, _cls_b, legacy_cls, _student_a, _student_b, _legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        counts = classes.student_counts()
        summaries = classes.list_class_summaries()

    assert counts == {cls_a.id: 1, legacy_cls.id: 1}
    assert {row.cls.id: row.student_count for row in summaries} == {
        cls_a.id: 1,
        legacy_cls.id: 1,
    }


# ---------------------------------------------------------------------------
# Reads: detail lookups raise NotFound for another campus
# ---------------------------------------------------------------------------


def test_detail_lookups_of_another_campus_raise_not_found(classes, students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, cls_b, legacy_cls, student_a, student_b, legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassNotFound):
            classes.get_class(cls_b.id)
        with pytest.raises(ClassNotFound):
            classes.class_summary(cls_b.id)
        with pytest.raises(ClassNotFound):
            students.class_name(cls_b.id)
        with pytest.raises(ClassNotFound):
            students.list_students(cls_b.id)
        with pytest.raises(StudentNotFound):
            students.get_student(student_b.id)
        assert classes.get_class(cls_a.id).id == cls_a.id
        assert classes.get_class(legacy_cls.id).id == legacy_cls.id
        assert students.get_student(student_a.id).id == student_a.id
        assert students.get_student(legacy_student.id).id == legacy_student.id


# ---------------------------------------------------------------------------
# Writes: stamping and cross-campus refusal
# ---------------------------------------------------------------------------


def test_create_class_stamps_the_acting_campus(classes, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        cls = classes.create_class(user=admin_a, name="Grade 1")

    row = session.query(Class).filter_by(id=cls.id).one()
    assert row.campus_id == campus_a.id


def test_create_class_rejects_a_foreign_campus_template(classes, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    template_b = FeeTemplate(name="B Standard", amount_cents=10000, campus_id=campus_b.id)
    legacy_template = FeeTemplate(name="Legacy Standard", amount_cents=10000)
    session.add_all([template_b, legacy_template])
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassError, match="valid fee template"):
            classes.create_class(
                user=admin_a, name="Grade 1", default_template_id=template_b.id
            )
        cls = classes.create_class(
            user=admin_a, name="Grade 1", default_template_id=legacy_template.id
        )

    assert cls.default_template_id == legacy_template.id


def test_set_default_template_rejects_a_foreign_campus_template(classes, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    template_b = FeeTemplate(name="B Standard", amount_cents=10000, campus_id=campus_b.id)
    session.add(template_b)
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        cls = classes.create_class(user=admin_a, name="Grade 1")
        with pytest.raises(ClassError, match="valid fee template"):
            classes.set_default_template(
                user=admin_a, class_id=cls.id, default_template_id=template_b.id
            )


def test_cross_campus_class_mutations_raise(classes, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassNotFound):
            classes.update_class(
                user=admin_a, class_id=cls_b.id, name="X", status="active"
            )
        with pytest.raises(ClassNotFound):
            classes.set_default_template(
                user=admin_a, class_id=cls_b.id, default_template_id=None
            )


def test_add_student_stamps_the_acting_campus(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, _cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        student = students.add_student(
            user=admin_a,
            class_id=cls_a.id,
            custom_amount=5000,
            first_name="Ada",
            last_name="Lovelace",
            enrolled_on="2026-01-15",
        )

    row = session.query(Student).filter_by(id=student.id).one()
    assert row.campus_id == campus_a.id
    change = session.query(StudentAmountChange).filter_by(student_id=student.id).one()
    assert change.campus_id == campus_a.id


def test_add_student_to_a_foreign_campus_class_raises(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassNotFound):
            students.add_student(
                user=admin_a,
                class_id=cls_b.id,
                custom_amount=5000,
                first_name="Ada",
                last_name="Lovelace",
            )


def test_add_student_rejects_a_foreign_campus_template(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, _cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)
    template_b = FeeTemplate(name="B Standard", amount_cents=10000, campus_id=campus_b.id)
    legacy_template = FeeTemplate(name="Legacy Standard", amount_cents=10000)
    session.add_all([template_b, legacy_template])
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(TemplateNotFound):
            students.add_student(
                user=admin_a,
                class_id=cls_a.id,
                fee_template_id=template_b.id,
                first_name="Ada",
                last_name="Lovelace",
            )
        student = students.add_student(
            user=admin_a,
            class_id=cls_a.id,
            fee_template_id=legacy_template.id,
            first_name="Ada",
            last_name="Lovelace",
        )

    assert student.fee_template_id == legacy_template.id


def test_cross_campus_student_mutations_raise(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, _cls_b, _legacy_cls, _student_a, student_b, _legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(StudentNotFound):
            students.update_student(
                user=admin_a, student_id=student_b.id, first_name="X", last_name="Y"
            )
        with pytest.raises(StudentNotFound):
            students.archive_student(user=admin_a, student_id=student_b.id)
        with pytest.raises(StudentNotFound):
            students.restore_student(user=admin_a, student_id=student_b.id)
        with pytest.raises(StudentNotFound):
            students.change_amount(
                user=admin_a, student_id=student_b.id, amount=7500, month=6, year=2026
            )
        with pytest.raises(StudentNotFound):
            students.set_template(
                user=admin_a, student_id=student_b.id, fee_template_id=1, month=6, year=2026
            )


def test_change_amount_stamps_the_acting_campus(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, _cls_b, _legacy_cls, student_a, _student_b, _legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(admin_a)):
        students.change_amount(
            user=admin_a, student_id=student_a.id, amount=7500, month=6, year=2026
        )

    change = session.query(StudentAmountChange).filter_by(student_id=student_a.id).one()
    assert change.campus_id == campus_a.id


def test_import_stamps_the_acting_campus(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a, _cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        students.import_students_csv(
            user=admin_a,
            class_id=cls_a.id,
            custom_amount=5000,
            content="Zara,Zulu\nMia,Moore\n",
        )

    rows = (
        session.query(Student)
        .filter(Student.first_name.in_(["Zara", "Mia"]))
        .order_by(Student.id)
        .all()
    )
    assert {s.full_name for s in rows} == {"Zara Zulu", "Mia Moore"}
    assert all(s.campus_id == campus_a.id for s in rows)
    changes = session.query(StudentAmountChange).all()
    assert all(c.campus_id == campus_a.id for c in changes)


def test_import_into_a_foreign_campus_class_raises(students, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _cls_a, cls_b, _legacy_cls, *_ = seed_classes_students(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassNotFound):
            students.import_students_csv(
                user=admin_a, class_id=cls_b.id, custom_amount=5000, content="Ada,Lovelace\n"
            )


# ---------------------------------------------------------------------------
# School-wide scope (Superadmin / Owner)
# ---------------------------------------------------------------------------


def test_superadmin_sees_both_campuses(classes, students, session):
    _school, campus_a, campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)
    cls_a, cls_b, legacy_cls, student_a, student_b, legacy_student = seed_classes_students(
        session, campus_a, campus_b
    )

    with scope_context(RequestScope.for_user(superadmin)):
        rows = classes.list_class_summaries()
        searched = students.search_students("")
        assert {row.cls.id for row in rows} == {cls_a.id, cls_b.id, legacy_cls.id}
        assert {row.id for row in searched} == {
            student_a.id,
            student_b.id,
            legacy_student.id,
        }
        assert classes.get_class(cls_a.id).id == cls_a.id
        assert classes.get_class(cls_b.id).id == cls_b.id
        assert students.get_student(student_a.id).id == student_a.id
        assert students.get_student(student_b.id).id == student_b.id


# ---------------------------------------------------------------------------
# RequestScope.for_user role resolution
# ---------------------------------------------------------------------------


def test_request_scope_for_user_resolves_each_role(session):
    school = School(name="Sunrise Academy")
    session.add(school)
    session.flush()
    campus = Campus(school_id=school.id, name="Campus A")
    session.add(campus)
    session.flush()
    admin = User(
        username="a",
        name="A",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
        school_id=school.id,
        campus_id=campus.id,
    )
    finance = User(
        username="f",
        name="F",
        password_hash=PASSWORD,
        role=UserRoles.FINANCE,
        school_id=school.id,
        campus_id=campus.id,
    )
    superadmin = User(
        username="s", name="S", password_hash=PASSWORD, role=UserRoles.SUPERADMIN,
        school_id=school.id,
    )
    owner = User(
        username="o", name="O", password_hash=PASSWORD, role=UserRoles.OWNER,
        school_id=school.id,
    )
    unbound = User(username="u", name="U", password_hash=PASSWORD, role=UserRoles.ADMIN)
    session.add_all([admin, finance, superadmin, owner, unbound])
    session.commit()

    assert RequestScope.for_user(admin).campus_id == campus.id
    assert RequestScope.for_user(finance).campus_id == campus.id
    super_scope = RequestScope.for_user(superadmin)
    assert super_scope.school_id == school.id
    assert super_scope.campus_id is None
    owner_scope = RequestScope.for_user(owner)
    assert owner_scope.school_id == school.id
    assert owner_scope.campus_id is None
    assert RequestScope.for_user(unbound) is None
    assert RequestScope.for_user(None) is None
