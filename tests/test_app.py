import asyncio
import base64
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import settings
from app import create_app
from conftest import BUILTIN, WAV, make_engine
from engine import EngineError
from options import SETTINGS
from tokens import TokenStore

BODY = {"text": "Hello there."}
SEEDED = {"text": "Hello there.", "seed": 5}
VOICES = sorted([*BUILTIN, "anna"])
ADMIN = {"X-Internal-Token": "admin"}
CLIP = {"audio_base64": base64.b64encode(WAV).decode(), "transcript": "What the clip says."}


def client(engine=None, admin_password=None, **options):
    return TestClient(create_app(engine or make_engine(), admin_password, **options))


def test_speak_returns_a_wav_with_its_length_voice_and_seed():
    engine = make_engine()
    reply = client(engine).post("/v1/speak", json={**SEEDED, "temperature": 0.5})
    assert reply.status_code == 200 and reply.headers["content-type"] == "audio/wav" and reply.content[:4] == b"RIFF"
    assert reply.headers["X-Audio-Seconds"] == "0.100" and reply.headers["X-Voice"] == "Bruno" and reply.headers["X-Seed"] == "5"
    assert int(reply.headers["X-Duration-Ms"]) >= 0
    call = engine.made[0].calls[0]
    assert call["text"] == "Hello there." and call["seed"] == 5 and call["temperature"] == 0.5 and call["preset"] == "stable"


def test_a_call_without_a_seed_gets_a_random_one_and_reports_it():
    engine = make_engine()
    c = client(engine, cache_size=4)
    first, second = c.post("/v1/speak", json=BODY), c.post("/v1/speak", json=BODY)
    assert first.headers["X-Seed"] != second.headers["X-Seed"]
    assert engine.made[0].calls[0]["seed"] == int(first.headers["X-Seed"])


def test_only_calls_with_a_seed_are_cached():
    engine = make_engine(voices=["anna"])
    c = client(engine, cache_size=4)
    assert [c.post("/v1/speak", json=BODY).headers["X-Cache"] for _ in range(2)] == ["miss", "miss"]
    first, second = c.post("/v1/speak", json=SEEDED), c.post("/v1/speak", json=SEEDED)
    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("miss", "hit")
    assert second.content == first.content and second.headers["X-Seed"] == "5"
    assert len(engine.made[0].calls) == 3
    c.post("/v1/speak", json={**SEEDED, "seed": 6})  # another seed, temperature, voice, preset or normalize is another answer
    c.post("/v1/speak", json={**SEEDED, "temperature": 0.9})
    c.post("/v1/speak", json={**SEEDED, "voice": "anna"})
    c.post("/v1/speak", json={**SEEDED, "preset": "expressive"})
    c.post("/v1/speak", json={**SEEDED, "normalize": False})
    assert len(engine.made[0].calls) == 8


def test_the_cache_keeps_only_the_newest_and_can_be_off():
    c = client(make_engine(), cache_size=1)
    for text in ("one", "two", "one"):
        assert c.post("/v1/speak", json={"text": text, "seed": 1}).headers["X-Cache"] == "miss"
    off = client(make_engine())  # no cache_size: off
    assert [off.post("/v1/speak", json=SEEDED).headers["X-Cache"] for _ in range(2)] == ["miss", "miss"]


def test_the_cache_is_not_used_after_the_model_was_reloaded():
    engine = make_engine()
    c = client(engine, cache_size=4)
    c.post("/v1/speak", json=SEEDED)
    asyncio.run(engine.unload())  # new weights
    assert c.post("/v1/speak", json=SEEDED).headers["X-Cache"] == "miss"


def test_cache_size_is_a_setting_that_applies_live(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    c = client(make_engine(), admin_password="admin", tokens=store, config=config)
    use = {"X-Internal-Token": c.post("/admin/tokens", json={"name": "t"}, headers=ADMIN).json()["token"]}
    assert [c.post("/v1/speak", json=SEEDED, headers=use).headers["X-Cache"] for _ in range(2)] == ["miss", "hit"]
    assert c.put("/admin/settings", json={"values": {"cache_size": 0}}, headers=ADMIN).status_code == 200
    assert c.post("/v1/speak", json=SEEDED, headers=use).headers["X-Cache"] == "miss"


def test_stream_sends_a_wav_without_a_length_and_the_audio_piece_by_piece():
    reply = client().post("/v1/speak", json={"text": " ".join(["word"] * 100), "stream": True})
    assert reply.status_code == 200 and reply.headers["content-type"] == "audio/wav" and reply.headers["X-Voice"] == "Bruno"
    assert reply.content[:4] == b"RIFF" and int.from_bytes(reply.content[24:28], "little") == 24000
    assert len(reply.content[44:]) == 2 * 4800
    assert reply.content[4:8] == b"\xff\xff\xff\xff" and reply.content[40:44] == b"\xff\xff\xff\xff"  # length unknown


def test_stream_errors_are_still_http_errors():
    c = client()
    assert c.post("/v1/speak", json={**BODY, "voice": "zz_nobody", "stream": True}).status_code == 404
    assert c.post("/v1/speak", json={"text": "...", "stream": True}).status_code == 422


def test_a_finished_seeded_stream_fills_the_cache_with_a_complete_wav():
    engine = make_engine()
    c = client(engine, cache_size=4)
    text = {"text": " ".join(["word"] * 100), "stream": True, "seed": 3}
    streamed = c.post("/v1/speak", json=text)
    kept = c.post("/v1/speak", json=text)
    assert (streamed.headers["X-Cache"], kept.headers["X-Cache"]) == ("miss", "hit")
    assert int.from_bytes(kept.content[40:44], "little") == 2 * 4800 and kept.content[44:] == streamed.content[44:]
    assert float(kept.headers["X-Audio-Seconds"]) == pytest.approx(0.2) and kept.headers["X-Seed"] == "3"
    assert len(engine.made[0].calls) == 1


def test_request_is_validated():
    c = client()
    assert c.post("/v1/speak", json={"text": ""}).status_code == 422
    assert c.post("/v1/speak", json={"text": "x" * 5001}).status_code == 422
    assert c.post("/v1/speak", json={**BODY, "temperature": 5}).status_code == 422
    assert c.post("/v1/speak", json={**BODY, "preset": "angry"}).status_code == 422  # the engine knows the presets
    assert c.post("/v1/speak", json={**BODY, "normalize": "maybe"}).status_code == 422
    assert c.post("/v1/speak", json={**BODY, "seed": -1}).status_code == 422
    assert c.post("/v1/speak", json={**BODY, "voice": "../etc"}).status_code == 422
    assert c.post("/v1/speak", json={**BODY, "speed": 1.2}).status_code == 422  # unknown fields are refused
    assert c.post("/v1/speak", json={**BODY, "format": "mp3"}).status_code == 422  # only WAV


def test_unknown_voice_is_404_and_a_crash_is_500():
    assert client().post("/v1/speak", json={**BODY, "voice": "zz_nobody"}).status_code == 404

    class Broken:
        async def synthesize(self, *args, **kwargs):
            raise error

        async def close(self):
            pass

        model, num_thread, ready, voices, default_voice, generation, device, store = "m", None, False, [], "Bruno", 0, "cpu", None

    for error, status in ((EngineError("too long", 413), 413), (RuntimeError("boom"), 500)):
        assert client(Broken()).post("/v1/speak", json=BODY).status_code == status


def test_health_and_voices():
    c = client(make_engine(voices=["anna"]))
    assert c.get("/health").json() == {"status": "ok", "model": "KittenML/kitten-tts-2", "ready": False,
                                       "num_thread": None, "device": "cpu", "voices": VOICES}
    assert c.get("/v1/voices").json() == {"voices": VOICES, "default": "Bruno"}
    c.post("/v1/speak", json=BODY)
    assert c.get("/health").json()["ready"] is True


def test_voices_are_added_and_removed_with_the_admin_password_and_used_at_once(tmp_path):
    engine = make_engine()
    c = client(engine, admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.put("/admin/voices/anna", json=CLIP).status_code == 401
    assert c.put("/admin/voices/anna", json=CLIP, headers=ADMIN).json() == {"voice": "anna", "bytes": len(WAV)}
    use = {"X-Internal-Token": c.post("/admin/tokens", json={"name": "t"}, headers=ADMIN).json()["token"]}
    assert c.get("/v1/voices", headers=use).json()["voices"] == VOICES
    assert c.post("/v1/speak", json={**BODY, "voice": "anna"}, headers=use).headers["X-Voice"] == "anna"
    assert engine.made[0].calls[0]["reference"][1] == "What the clip says."
    assert c.delete("/admin/voices/anna", headers=use).status_code == 401  # a caller token is not the admin password
    assert c.delete("/admin/voices/anna", headers=ADMIN).status_code == 200
    assert c.delete("/admin/voices/anna", headers=ADMIN).status_code == 404
    assert c.post("/v1/speak", json={**BODY, "voice": "anna"}, headers=use).status_code == 404


def test_admin_lists_voices_with_their_origin(tmp_path):
    c = client(make_engine(), admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.get("/admin/voices").status_code == 401
    c.put("/admin/voices/anna", json=CLIP, headers=ADMIN)
    data = c.get("/admin/voices", headers=ADMIN).json()
    assert {v["name"]: v["cloned"] for v in data["voices"]}["anna"] is True
    assert [v["name"] for v in data["voices"] if not v["cloned"]]  # built-in (or "none") voices cannot be deleted
    assert data["default"]


def test_bad_voice_uploads_are_422(tmp_path):
    engine = make_engine()
    c = client(engine, admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.put("/admin/voices/Bruno", json=CLIP, headers=ADMIN).status_code == 409  # a built-in voice keeps its name
    for name, body in (("anna", {**CLIP, "audio_base64": "!!not base64!!"}),
                       ("anna", {**CLIP, "audio_base64": base64.b64encode(b"not a wav file").decode()}),
                       ("anna", {**CLIP, "transcript": " "}), ("anna", {**CLIP, "extra": 1})):
        assert c.put(f"/admin/voices/{name}", json=body, headers=ADMIN).status_code == 422
    assert engine.voices == BUILTIN


ONE_CALL = {"reference_audio_base64": base64.b64encode(WAV).decode(), "reference_text": "What the clip says."}


@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    """The folder temp files go to, so a test can see that nothing is left in it."""
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(folder))
    return folder


@pytest.mark.parametrize("stream", [False, True])
def test_a_one_call_reference_is_used_then_deleted_and_never_stored_or_cached(temp_dir, stream):
    engine = make_engine()
    c = client(engine, cache_size=4)
    body = {**SEEDED, **ONE_CALL, "stream": stream}
    first, second = c.post("/v1/speak", json=body), c.post("/v1/speak", json=body)
    assert first.status_code == 200 and first.headers["X-Voice"] == "custom"
    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("miss", "miss")  # a cloned voice is never cached
    assert [call["reference_bytes"] for call in engine.made[0].calls] == [WAV, WAV]
    assert engine.made[0].calls[0]["reference"][1] == "What the clip says."
    assert list(temp_dir.iterdir()) == [] and engine.store.names() == []
    assert not (engine.store.folder.exists() and any(engine.store.folder.iterdir()))


@pytest.mark.parametrize("stream", [False, True])
def test_a_one_call_reference_is_deleted_when_the_model_fails(temp_dir, stream):
    engine = make_engine()
    c = client(engine)
    c.post("/v1/speak", json=BODY)  # loads the fake model
    engine.made[0].fail = True
    assert c.post("/v1/speak", json={**BODY, **ONE_CALL, "stream": stream}).status_code >= 400
    assert list(temp_dir.iterdir()) == []


def test_a_bad_one_call_reference_is_refused_before_any_work(temp_dir):
    engine = make_engine()
    c = client(engine)
    audio, text = ONE_CALL["reference_audio_base64"], ONE_CALL["reference_text"]
    for extra in ({"reference_audio_base64": audio}, {"reference_text": text}, {**ONE_CALL, "voice": BUILTIN[0]},
                  {**ONE_CALL, "reference_audio_base64": "!!not base64!!"},
                  {**ONE_CALL, "reference_audio_base64": base64.b64encode(b"not a wav file").decode()},
                  {**ONE_CALL, "reference_text": " "}):
        assert c.post("/v1/speak", json={**BODY, **extra}).status_code == 422
    assert not engine.made and list(temp_dir.iterdir()) == []


def test_a_one_call_reference_may_be_a_data_url_as_the_try_it_panel_sends(temp_dir):
    engine = make_engine()
    url = "data:audio/wav;base64," + ONE_CALL["reference_audio_base64"]
    reply = client(engine).post("/v1/speak", json={**BODY, **ONE_CALL, "reference_audio_base64": url})
    assert reply.status_code == 200 and engine.made[0].calls[0]["reference_bytes"] == WAV
    assert list(temp_dir.iterdir()) == []


def test_a_token_limited_to_voices_may_not_send_its_own_reference(tmp_path):
    c = client(make_engine(), admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    limited = {"X-Internal-Token": c.post("/admin/tokens", json={"name": "p", "projects": [BUILTIN[0]]}, headers=ADMIN).json()["token"]}
    free = {"X-Internal-Token": c.post("/admin/tokens", json={"name": "f"}, headers=ADMIN).json()["token"]}
    assert c.post("/v1/speak", json={**BODY, **ONE_CALL}, headers=limited).status_code == 403
    assert c.post("/v1/speak", json={**BODY, **ONE_CALL}, headers=free).status_code == 200


def test_each_caller_gets_its_own_revocable_token(tmp_path):
    c = client(admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.post("/v1/speak", json=BODY).status_code == 401
    made = c.post("/admin/tokens", json={"name": "Garrison"}, headers=ADMIN).json()
    assert made["token"].startswith("kitten2_")
    use = {"X-Internal-Token": made["token"]}
    assert c.post("/v1/speak", json=BODY, headers=use).status_code == 200
    assert c.delete(f"/admin/tokens/{made['id']}", headers=ADMIN).status_code == 200
    assert c.post("/v1/speak", json=BODY, headers=use).status_code == 401
    assert c.get("/health").status_code == 200  # /health needs no token


def test_a_token_limited_to_voices_refuses_the_others(tmp_path):
    c = client(make_engine(voices=["anna", "bob"]), admin_password="admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.post("/admin/tokens", json={"name": "x", "projects": ["bad name"]}, headers=ADMIN).status_code == 422
    made = c.post("/admin/tokens", json={"name": "p", "projects": ["anna"]}, headers=ADMIN).json()
    use = {"X-Internal-Token": made["token"]}
    assert c.post("/v1/speak", json={**BODY, "voice": "anna"}, headers=use).status_code == 200
    assert c.post("/v1/speak", json={**BODY, "voice": "bob"}, headers=use).status_code == 403
    assert c.post("/v1/speak", json=BODY, headers=use).status_code == 403  # the default voice, Bruno, is not in its list
    assert c.get("/v1/voices", headers=use).json()["voices"] == ["anna"]
    both = c.post("/admin/tokens", json={"name": "q", "projects": ["Bruno"]}, headers=ADMIN).json()
    assert c.post("/v1/speak", json=BODY, headers={"X-Internal-Token": both["token"]}).status_code == 200


def test_rate_limit_edit_stats_and_metrics(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    c = client(admin_password="admin", tokens=store)
    made = c.post("/admin/tokens", json={"name": "p", "rate": 1}, headers=ADMIN).json()
    use = {"X-Internal-Token": made["token"]}
    assert c.post("/v1/speak", json=BODY, headers=use).status_code == 200
    limited = c.post("/v1/speak", json=BODY, headers=use)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert c.put(f"/admin/tokens/{made['id']}", json={"projects": None, "rate": None}, headers=ADMIN).status_code == 200
    assert c.post("/v1/speak", json=BODY, headers=use).status_code == 200  # the limit is gone
    assert c.put("/admin/tokens/nope", json={}, headers=ADMIN).status_code == 404
    assert store.list()[0]["timed"] >= 1
    assert c.get("/metrics").status_code == 401
    assert 'kitten2_requests_total{token="p"}' in c.get("/metrics", headers=ADMIN).text
    assert 'kitten2_request_seconds_bucket{le="+Inf"}' in c.get("/metrics", headers=ADMIN).text


def test_requests_over_the_in_flight_limit_get_429():
    async def main():
        engine = make_engine()
        release = asyncio.Event()
        real = engine.synthesize

        async def slow(*args, **kwargs):
            await release.wait()
            return await real(*args, **kwargs)

        engine.synthesize = slow
        app = create_app(engine, max_inflight=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://svc") as http:
            first = asyncio.create_task(http.post("/v1/speak", json=BODY))
            await asyncio.sleep(0.2)
            second = await http.post("/v1/speak", json=BODY)
            release.set()
            return second, await first

    second, first = asyncio.run(main())
    assert second.status_code == 429 and second.headers["Retry-After"] == "5"
    assert first.status_code == 200


def test_workers_are_read_only_and_admin_only(monkeypatch):
    monkeypatch.setenv("SERVICE_REPLICAS", "3")
    c = client(admin_password="admin")
    assert c.get("/admin/workers").status_code == 401
    assert c.get("/admin/workers", headers=ADMIN).json() == {"replicas": 3, "parallel": 1}


def test_num_thread_is_reported_and_set_by_the_admin(tmp_path):
    engine = make_engine()
    c = client(engine, "admin", tokens=TokenStore(tmp_path / "t.json"))
    assert c.put("/admin/threads", json={"num_thread": 0}, headers=ADMIN).status_code == 422
    assert c.put("/admin/threads", json={"num_thread": 3}, headers=ADMIN).json() == {"num_thread": 3}
    assert c.get("/health").json()["num_thread"] == 3
    assert settings.load(tmp_path / "settings.json")["num_thread"] == 3


def test_settings_are_admin_only_checked_and_apply_live(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    c = client(admin_password="admin", tokens=store, config=config)
    assert c.get("/admin/settings").status_code == 401
    assert c.put("/admin/settings", json={"values": {"max_inflight": -1}}, headers=ADMIN).status_code == 422
    assert c.put("/admin/settings", json={"values": {"max_inflight": 7}}, headers=ADMIN).status_code == 200
    saved = {item["key"]: item for item in c.get("/admin/settings", headers=ADMIN).json()["settings"]}
    assert saved["max_inflight"]["value"] == 7 and saved["model_revision"]["value"] == "c93cb7c271baa51d9ae8204d5277988906f235a2"
    assert client(admin_password="admin").put("/admin/settings", json={"values": {}}, headers=ADMIN).status_code == 409


def test_what_another_replica_saved_reaches_this_one(tmp_path):
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    engine = make_engine()
    with TestClient(create_app(engine, "admin", tokens=store, config=config)):
        settings.save(store.settings_path, num_thread=5)
        for _ in range(300):  # the loop looks every second
            if engine.num_thread == 5:
                break
            time.sleep(0.02)
    assert engine.num_thread == 5


def test_startup_warms_the_model():
    engine = make_engine()
    with TestClient(create_app(engine, warm=True)) as c:
        for _ in range(100):
            if c.get("/health").json()["ready"]:
                break
            time.sleep(0.02)
        assert len(engine.loads) == 1 and c.get("/health").json()["ready"] is True


def test_health_answers_while_the_model_is_still_loading():
    import threading
    release = threading.Event()

    def slow(*args):
        release.wait(5)
        return make_engine()._loader(*args)

    with TestClient(create_app(make_engine(loader=slow), warm=True)) as c:
        assert c.get("/health").json()["ready"] is False
        release.set()


def test_warmup_failure_is_logged_without_stopping_service(caplog):
    def failing(*args):
        raise RuntimeError("no model")

    with TestClient(create_app(make_engine(loader=failing), warm=True)) as c:
        assert c.get("/health").status_code == 200
        for _ in range(100):
            if "warm-up failed" in caplog.text:
                break
            time.sleep(0.02)
    assert "warm-up failed" in caplog.text


def test_warmup_is_optional():
    engine = make_engine()
    with TestClient(create_app(engine)):
        assert engine.loads == []


def test_main_builds_the_engine_from_settings(monkeypatch, tmp_path):
    import app as module

    monkeypatch.setenv("SERVICE_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("SERVICE_NUM_THREAD", "2")
    monkeypatch.setenv("SERVICE_DEVICE", "cpu")
    monkeypatch.setenv("SERVICE_WEIGHTS", "emb4")
    monkeypatch.setenv("SERVICE_MODEL_REVISION", "abc")
    monkeypatch.setenv("SERVICE_PORT", "9999")
    seen, started = [], {}
    monkeypatch.setattr(module, "create_app", lambda client, **kwargs: seen.append(client) or "app")
    monkeypatch.setattr("uvicorn.Server.run", lambda self: started.update(app=self.config.app, host=self.config.host, port=self.config.port))
    module.main()
    assert started["port"] == 9999 and started["host"] == "127.0.0.1"
    engine = seen[0]
    assert engine.num_thread == 2 and engine.revision == "abc" and (engine.device, engine.weights) == ("cpu", "emb4")
    assert engine.max_new_tokens == 1000
