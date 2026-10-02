"""Who may see or change a run or a project (spec section 5, Access rules).

Rules over plain dicts so pages and services share one implementation:
  can_view_run     = run.public or run is a baseline or owner or admin
  can_modify_run   = owner or admin (never for a baseline)
  can_modify_project = owner or admin (a system example only by admin)
  can_use_project  = logged in and (owner or admin or a system example)
Every read path calls the view rule and every mutation the modify rule
inside the service, raising NotAllowed otherwise.
"""

from __future__ import annotations

from sfincs_ui.exceptions import NotAllowed
from sfincs_ui.models.user import ROLE_ADMIN


def _active(user: dict | None) -> bool:
    # Absent means active (service dicts always carry the key); None, 0 and False mean inactive.
    return bool(user) and bool(user.get("is_active", True))


def is_admin(user: dict | None) -> bool:
    return _active(user) and user.get("role") == ROLE_ADMIN


def _owns(user: dict | None, owner_id) -> bool:
    return _active(user) and owner_id is not None and user.get("id") == owner_id


def can_view_run(user: dict | None, run: dict) -> bool:
    if run.get("public") or run.get("baseline"):
        return True
    return _owns(user, run.get("owner_id")) or is_admin(user)


def can_modify_run(user: dict | None, run: dict) -> bool:
    if run.get("baseline"):
        return False
    return _owns(user, run.get("owner_id")) or is_admin(user)


def can_modify_project(user: dict | None, project: dict) -> bool:
    return _owns(user, project.get("owner_id")) or is_admin(user)


def can_use_project(user: dict | None, project: dict) -> bool:
    if not _active(user):
        return False
    return project.get("owner_id") is None or _owns(user, project.get("owner_id")) or is_admin(user)


def require_user(user: dict | None) -> dict:
    if not _active(user):
        raise NotAllowed("Log in to do this")
    return user


def require_view_run(user: dict | None, run: dict) -> None:
    if not can_view_run(user, run):
        raise NotAllowed("You may not view this run")


def require_modify_run(user: dict | None, run: dict) -> None:
    if not can_modify_run(user, run):
        raise NotAllowed("Only the run's owner or an administrator may do this")


def require_modify_project(user: dict | None, project: dict) -> None:
    if not can_modify_project(user, project):
        raise NotAllowed("Only the project's owner or an administrator may do this")


def require_use_project(user: dict | None, project: dict) -> None:
    if not can_use_project(user, project):
        raise NotAllowed("You may not use this project")
