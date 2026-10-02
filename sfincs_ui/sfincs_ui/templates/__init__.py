from sfincs_ui.exceptions import TemplateError
from sfincs_ui.templates.base import SettingField, Template
from sfincs_ui.templates.plane_beach import PlaneBeachTemplate

TEMPLATES: dict[str, Template] = {t.key: t for t in (PlaneBeachTemplate(),)}


def get_template(key: str) -> Template:
    try:
        return TEMPLATES[key]
    except KeyError:
        raise TemplateError(f"unknown template {key!r}") from None


__all__ = ["TEMPLATES", "get_template", "SettingField", "Template", "PlaneBeachTemplate"]
