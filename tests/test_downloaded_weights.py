"""Downloaded-only loading and explicit admin downloads, without network calls."""
import pytest
from fastapi.testclient import TestClient

from app import create_app
from conftest import make_engine


def test_missing_weights_keep_admin_and_health_available_then_download_recovers():
    state = {"downloaded": False, "downloads": 0}
    normal = make_engine()
    original = normal._loader

    def local_loader(*args):
        if not state["downloaded"]:
            raise OSError("private/cache/location: weights missing")
        return original(*args)

    def download(*args):
        state["downloads"] += 1
        state["downloaded"] = True

    engine = make_engine(loader=local_loader, download=download,
                         cached_sha=lambda *args: "old" if state["downloaded"] else None,
                         remote_sha=lambda *args: "new")
    admin = {"X-Internal-Token": "admin"}
    with TestClient(create_app(engine, admin_password="admin", warm=True)) as client:
        token = client.post("/admin/tokens", json={"name": "caller"}, headers=admin).json()["token"]
        caller = {"X-Internal-Token": token}
        assert client.get("/health").json()["ready"] is False
        assert client.get("/admin/").status_code == 200
        for streaming in (False, True):
            missing = client.post("/v1/speak", json={"text": "Hello.", "stream": streaming}, headers=caller)
            assert missing.status_code == 503
            assert "Download" in missing.json()["detail"] and "Updates" in missing.json()["detail"]
            assert "private" not in missing.text and "http" not in missing.text
        assert state["downloads"] == 0
        check = client.post("/admin/updates/check", headers=admin).json()
        assert check["weights"][0]["update"] is True
        assert state["downloads"] == 0
        assert client.post("/admin/updates/weights", headers=admin).status_code == 200
        assert state["downloads"] == 1
        assert client.post("/v1/speak", json={"text": "Hello."}, headers=caller).status_code == 200
        assert client.get("/health").json()["ready"] is True

def test_audio8_loader_never_downloads_missing_weights(monkeypatch):
    import sys
    import types
    import engine

    def cached_only(*args, **kwargs):
        assert kwargs.get("local_files_only") is True
        assert kwargs["revision"] == "pinned"
        raise OSError("missing")

    fake = types.SimpleNamespace(from_pretrained=cached_only)
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(AutoModel=fake, AutoProcessor=fake))
    with pytest.raises(OSError):
        engine.load("m", "pinned", "cpu", "float32")

def test_download_fetches_pinned_snapshot(monkeypatch):
    import huggingface_hub
    import engine
    calls = []
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *args, **kwargs: calls.append((args, kwargs)))
    engine._download("model", "pinned")
    assert calls == [(("model",), {"revision": "pinned", "token": False})]
