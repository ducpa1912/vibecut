"""Lane guard: new routes live in lane modules, so lanes rarely edit app.py."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Routes defined directly in app.py when the lane rule started. Lower it when
#: a route moves out; never raise it. New routes go into routes_classic.py,
#: routes_studio.py or routes_voice_clone.py (docs/branching.md).
APP_ROUTE_CEILING = 104


def test_app_py_gains_no_new_routes():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    count = len(re.findall(r"^@app\.(get|post|put|patch|delete|api_route)\(", text, re.M))
    assert count <= APP_ROUTE_CEILING, (
        f"app.py has {count} routes (ceiling {APP_ROUTE_CEILING}). "
        "Put new routes in the lane module: routes_classic.py, routes_studio.py "
        "or routes_voice_clone.py."
    )


def test_lane_modules_are_registered():
    import app
    import routes_classic
    import routes_studio
    import routes_voice_clone

    text = (ROOT / "app.py").read_text(encoding="utf-8")
    for module in (routes_classic, routes_studio, routes_voice_clone):
        assert f"app.include_router({module.__name__}.router)" in text
