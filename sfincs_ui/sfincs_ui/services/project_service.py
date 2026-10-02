"""Projects: a template plus a settings document, owned by a user, with a workspace directory."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sfincs_ui.config import Config
from sfincs_ui.exceptions import NotAllowed, NotFound, TemplateError
from sfincs_ui.models import Project, Run, User, new_id
from sfincs_ui.services import access_control as ac

MAX_NAME = 100
_ACTIVE_RUN_STATUSES = ("queued", "building", "running", "validating", "exporting")


class ProjectService:
    def __init__(self, config: Config, session_factory=None, templates=None):
        if session_factory is None:
            from sfincs_ui.db.base import get_session_factory
            session_factory = get_session_factory()
        if templates is None:
            from sfincs_ui.templates import TEMPLATES
            templates = TEMPLATES
        self._config = config
        self._sf = session_factory
        self._templates = templates

    def _template(self, key: str):
        try:
            return self._templates[key]
        except KeyError:
            raise TemplateError(f"unknown template {key!r}") from None

    def project_dir(self, project_id: str) -> Path:
        return self._config.workspace / project_id

    def _to_dict(self, p: Project, session) -> dict:
        owner = session.get(User, p.owner_id) if p.owner_id else None
        tpl = self._templates.get(p.template)
        return {"id": p.id, "owner_id": p.owner_id, "owner": owner.username if owner else None, "name": p.name,
                "template": p.template, "template_title": tpl.title if tpl else p.template,
                "settings": json.loads(p.settings_json), "created_at": p.created_at, "updated_at": p.updated_at,
                "run_count": session.query(Run).filter(Run.project_id == p.id).count()}

    def _get_row(self, session, project_id: str) -> Project:
        p = session.get(Project, project_id)
        if p is None:
            raise NotFound("Project not found")
        return p

    # -- examples ----------------------------------------------------------

    def ensure_examples(self) -> int:
        created = 0
        s = self._sf()
        try:
            for tpl in self._templates.values():
                for name, settings in tpl.example_projects():
                    exists = s.query(Project).filter(Project.owner_id.is_(None), Project.template == tpl.key, Project.name == name).first()
                    if exists is None:
                        p = Project(id=new_id(), owner_id=None, name=name, template=tpl.key, settings_json=json.dumps(tpl.validate(settings)))
                        s.add(p); s.flush()
                        self.project_dir(p.id).mkdir(parents=True, exist_ok=True)
                        created += 1
            s.commit()
            return created
        finally:
            s.close()

    def examples(self) -> list[dict]:
        s = self._sf()
        try:
            rows = s.query(Project).filter(Project.owner_id.is_(None)).order_by(Project.name).all()
            return [self._to_dict(p, s) for p in rows]
        finally:
            s.close()

    # -- CRUD --------------------------------------------------------------

    def list_for(self, user: dict | None) -> list[dict]:
        if not user:
            return []
        s = self._sf()
        try:
            rows = s.query(Project).filter(Project.owner_id == user["id"]).order_by(Project.created_at.desc()).all()
            return [self._to_dict(p, s) for p in rows]
        finally:
            s.close()

    def get(self, user: dict | None, project_id: str) -> dict:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            d = self._to_dict(p, s)
            ac.require_use_project(user, d)
            return d
        finally:
            s.close()

    def create(self, user: dict | None, template_key: str, name: str, settings: dict | None = None) -> dict:
        ac.require_user(user)
        tpl = self._template(template_key)
        name = _clean_name(name)
        s = self._sf()
        try:
            p = Project(id=new_id(), owner_id=user["id"], name=name, template=tpl.key,
                        settings_json=json.dumps(tpl.validate(settings or {})))
            s.add(p); s.commit()
            self.project_dir(p.id).mkdir(parents=True, exist_ok=True)
            return self._to_dict(p, s)
        finally:
            s.close()

    def clone(self, user: dict | None, project_id: str, new_name: str) -> dict:
        src = self.get(user, project_id)  # require_use_project: examples and own projects
        return self.create(user, src["template"], new_name, src["settings"])

    def rename(self, user: dict | None, project_id: str, name: str) -> dict:
        name = _clean_name(name)
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            p.name = name; s.commit()
            return self._to_dict(p, s)
        finally:
            s.close()

    def update_settings(self, user: dict | None, project_id: str, settings: dict) -> dict:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            p.settings_json = json.dumps(self._template(p.template).validate(settings)); s.commit()
            return self._to_dict(p, s)
        finally:
            s.close()

    def delete(self, user: dict | None, project_id: str) -> None:
        s = self._sf()
        try:
            p = self._get_row(s, project_id)
            ac.require_modify_project(user, self._to_dict(p, s))
            if s.query(Run).filter(Run.project_id == p.id, Run.status.in_(_ACTIVE_RUN_STATUSES)).count():
                raise NotAllowed("This project has an active run; cancel it first")
            s.delete(p); s.commit()
        finally:
            s.close()
        shutil.rmtree(self.project_dir(project_id), ignore_errors=True)


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        raise TemplateError(f"name must be 1-{MAX_NAME} characters")
    return name
