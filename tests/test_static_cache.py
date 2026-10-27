"""Studio modules must revalidate so an update never mixes old and new code."""

from fastapi.testclient import TestClient

import app


def test_static_files_are_revalidated_on_every_load():
    client = TestClient(app.app)
    response = client.get("/static/studio/shell.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers.get("etag")
    again = client.get("/static/studio/shell.js", headers={"If-None-Match": response.headers["etag"]})
    assert again.status_code == 304
