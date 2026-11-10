"""Looks (themes) for the site.

Built-in themes ship with Merchant. Extra themes can be dropped into
app/static/themes-local/ as <name>.css; git ignores that folder, so a theme
there stays on that machine only.
"""
from pathlib import Path

from flask import current_app, request

BUILT_IN = {
    "classic": {"label": "Classic", "css": None},
    "orbit": {"label": "Orbit", "css": "css/themes/orbit.css"},
}
LOCAL_FOLDER = "themes-local"


def available_themes():
    themes = dict(BUILT_IN)
    folder = Path(current_app.static_folder) / LOCAL_FOLDER
    if folder.is_dir():
        for css in sorted(folder.glob("*.css")):
            name = css.stem.lower()
            if name not in themes and name.replace("-", "").replace("_", "").isalnum():
                label = name.replace("-", " ").replace("_", " ").title()
                themes[name] = {"label": label, "css": f"{LOCAL_FOLDER}/{css.name}"}
    return themes


def current_theme(themes=None):
    themes = themes or available_themes()
    for choice in (request.cookies.get("theme"), current_app.config["DEFAULT_THEME"], "orbit"):
        if choice in themes:
            return choice
    return "classic"
