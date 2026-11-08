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

def test_kitten_loader_never_downloads_missing_weights(monkeypatch):
    import sys
    import types
    import huggingface_hub
    import engine

    def cached_only(*args, **kwargs):
        assert kwargs.get("local_files_only") is True
        assert kwargs["revision"] == "pinned"
        raise OSError("missing")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", cached_only)
    monkeypatch.setitem(sys.modules, "kittenml", types.ModuleType("kittenml"))
    monkeypatch.setitem(sys.modules, "kittenml.get_model", types.SimpleNamespace(_kitten2_files=lambda *args: []))
    with pytest.raises(OSError):
        engine._snapshot("m", "pinned", "packed", "default")

def test_download_fetches_pinned_config_and_selected_files(monkeypatch, tmp_path):
    import sys
    import types
    import huggingface_hub
    import engine
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    calls = []
    def config_download(*args, **kwargs):
        calls.append((args, kwargs))
        return str(config)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", config_download)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "kittenml", types.ModuleType("kittenml"))
    monkeypatch.setitem(sys.modules, "kittenml.get_model", types.SimpleNamespace(_kitten2_files=lambda config, decoder, weights: ["config.json", "lm/*"]))
    engine._download("model", "pinned", "packed", "default")
    assert calls[0] == (("model", "config.json"), {"revision": "pinned", "token": False})
    assert calls[1] == (("model",), {"revision": "pinned", "allow_patterns": ["config.json", "lm/*"], "token": False})
