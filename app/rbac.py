"""Role-based access control.

Every chunk carries two labels: its `department` and its `access_level`
(0 = public, 1 = internal, 2 = confidential). A user has a role and a home department.

    employee : public docs of every department + internal docs of their own department
    manager  : public and internal docs of every department + confidential docs of their own department
    admin    : everything

The rule is written twice on purpose:
- `can_read()` is plain Python. It is the reference definition, used by the tests.
- `qdrant_filter()` is the same rule expressed as a Qdrant filter, so unauthorised chunks
  are excluded INSIDE the database search and never reach the application or the LLM.
The leakage test checks that the two always agree.
"""

from dataclasses import dataclass
from enum import IntEnum

from qdrant_client import models


class Level(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2


DEPARTMENTS = ("hr", "engineering", "finance", "sales")
ROLES = ("employee", "manager", "admin")


@dataclass(frozen=True)
class User:
    username: str
    role: str
    department: str
    full_name: str = ""


# Demo users. Every password is "demo". In a real system these come from your identity provider.
DEMO_USERS: dict[str, User] = {
    "priya": User("priya", "employee", "engineering", "Priya Sharma"),
    "ananya": User("ananya", "employee", "sales", "Ananya Iyer"),
    "rahul": User("rahul", "manager", "finance", "Rahul Mehta"),
    "vikram": User("vikram", "manager", "hr", "Vikram Rao"),
    "admin": User("admin", "admin", "it", "Admin"),
}


def can_read(user: User, department: str, access_level: int) -> bool:
    """Reference rule: may this user see a chunk with these labels?"""
    if user.role == "admin":
        return True
    if user.role == "manager":
        return access_level <= Level.INTERNAL or (department == user.department and access_level <= Level.CONFIDENTIAL)
    if user.role == "employee":
        return access_level <= Level.PUBLIC or (department == user.department and access_level <= Level.INTERNAL)
    return False


def _rule(max_level: int, department: str | None = None) -> models.Filter:
    must: list[models.Condition] = [models.FieldCondition(key="access_level", range=models.Range(lte=max_level))]
    if department is not None:
        must.append(models.FieldCondition(key="department", match=models.MatchValue(value=department)))
    return models.Filter(must=must)


def qdrant_filter(user: User) -> models.Filter | None:
    """The same rule as `can_read`, as a Qdrant filter. `should` means OR."""
    if user.role == "admin":
        return None
    if user.role == "manager":
        return models.Filter(should=[_rule(Level.INTERNAL), _rule(Level.CONFIDENTIAL, user.department)])
    if user.role == "employee":
        return models.Filter(should=[_rule(Level.PUBLIC), _rule(Level.INTERNAL, user.department)])
    # Unknown role: match nothing.
    return models.Filter(must=[models.FieldCondition(key="access_level", range=models.Range(lt=-1))])
