"""Seed an isolated SQLite DB for the visual verification pass (ticket 08)."""
import os
from datetime import date, timedelta

os.environ["SCHOOL_FINANCE_DATA"] = r"C:\Users\Geesey\AppData\Local\Temp\opencode\sf-visual"
os.environ.pop("DATABASE_URL", None)

from app.core.scope import scope_context, RequestScope
from app.db import Database
from app.models import Base
from app.services.auth import AuthService
from app.tenants.service import TenantService
from app.classes.service import ClassService  # noqa: F401
from app.fees.service import FeeService
from app.students.service import StudentService
from app.payments.service import PaymentService
from app.arrears.service import ArrearsService

DATA = r"C:\Users\Geesey\AppData\Local\Temp\opencode\sf-visual"
os.makedirs(DATA, exist_ok=True)
db_path = os.path.join(DATA, "school_finance.db")
if os.path.exists(db_path):
    os.remove(db_path)

os.environ["SCHOOL_FINANCE_DB"] = db_path
import app.config as config  # noqa: E402

print("DB:", config.DATABASE_URL)
