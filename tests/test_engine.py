import asyncio

import pytest

from conftest import BUILTIN, make_engine
from engine import DEFAULT_REVISION, DEFAULT_VOICE, EngineError

LOAD = (DEFAULT_REVISION, "cpu", "packed", "default")


def speak(engine, text="hello", voice=None, seed=1, temperature=None, preset=None, normalize=True):
    return asyncio.run(engine.synthesize(text, voice, seed, temperature, preset, normalize))


def collect(engine, text="One. Two.", voice=None, seed=1, temperature=None, preset=None, normalize=True):
    async def run():
        return [piece async for piece in engine.stream(text, voice, seed, temperature, preset, normalize)]

    return asyncio.run(run())


def test_the_model_loads_once_with_the_pinned_revision_and_speaks_the_default_voice():
    engine = make_engine()
    assert engine.voices == BUILTIN and engine.default_voice == DEFAULT_VOICE == "Bruno" and not engine.ready
    first = speak(engine)
    speak(engine, "again")
    assert first["voice"] == "Bruno" and first["seconds"] == pytest.approx(0.1) and first["wav"][:4] == b"RIFF"
    assert engine.loads == [LOAD] and engine.ready
    calls = engine.made[0].calls
    assert [call["text"] for call in calls] == ["hello", "again"] and calls[0]["reference"] is None and calls[0]["voice"] == "Bruno"
    assert calls[0]["preset"] == "stable" and calls[0]["normalize"] is True and calls[0]["max_new_tokens"] == 1000


def test_a_built_in_voice_and_options_reach_the_model():
    engine = make_engine()
    assert speak(engine, voice="Kiki", seed=7, temperature=0.5, preset="expressive", normalize=False)["voice"] == "Kiki"
    call = engine.made[0].calls[0]
    assert (call["voice"], call["seed"], call["temperature"], call["preset"], call["normalize"]) == ("Kiki", 7, 0.5, "expressive", False)


def test_a_cloned_voice_gives_the_model_its_clip_and_transcript_and_is_listed_with_the_built_in_ones():
    engine = make_engine(voices=["anna"])
    assert engine.voices == sorted([*BUILTIN, "anna"])
    assert speak(engine, voice="anna")["voice"] == "anna"
    path, text = engine.made[0].calls[0]["reference"]
    assert path.name == "anna.wav" and text == "Transcript of anna."


def test_before_the_first_download_only_the_default_voice_is_known():
    assert make_engine(names=lambda *_: []).voices == ["Bruno"]


def test_an_unknown_voice_is_404_and_an_unknown_preset_is_422():
    for call in (lambda: speak(make_engine(), voice="zz_nobody"), lambda: collect(make_engine(), voice="zz_nobody")):
        with pytest.raises(EngineError) as error:
            call()
        assert error.value.status == 404
    with pytest.raises(EngineError) as error:
        speak(make_engine(), preset="angry")
    assert error.value.status == 422


def test_text_the_model_cannot_speak_is_422():
    for call in (lambda: speak(make_engine(), "..."), lambda: collect(make_engine(), "...")):
        with pytest.raises(EngineError) as error:
            call()
        assert error.value.status == 422


def test_stream_gives_the_audio_piece_by_piece():
    pieces = collect(make_engine())
    assert [rate for rate, _ in pieces] == [24000, 24000] and all(len(data) == 4800 for _, data in pieces)


def test_closing_a_stream_early_frees_the_generation_slot():
    async def run():
        engine = make_engine()
        pieces = engine.stream("One. Two.", None, 1, None)
        await anext(pieces)
        await pieces.aclose()
        return await asyncio.wait_for(engine.synthesize("again", None, 1, None), 2)

    assert asyncio.run(run())["seconds"] == pytest.approx(0.1)


def test_a_new_download_by_another_replica_drops_the_loaded_model(tmp_path):
    marker = tmp_path / "marker"
    one, two = make_engine(marker=marker), make_engine(marker=marker)
    speak(one)
    asyncio.run(two.unload())
    one.sync()
    assert not one.ready
    speak(one)
    assert len(one.loads) == 2


def test_the_revision_calls_use_the_model_and_revision():
    engine = make_engine(revision="abc", cached_sha=lambda model, rev: f"cached-{rev}", remote_sha=lambda model, rev: f"latest-{rev}")
    assert asyncio.run(engine.cached_sha()) == "cached-abc" and asyncio.run(engine.remote_sha()) == "latest-abc"


def test_the_download_gets_the_weights_and_decoder_to_fetch():
    seen = []
    engine = make_engine(weights="emb4", decoder="student_w4", download=lambda *args: seen.append(args))
    asyncio.run(engine.pull())
    assert seen == [("KittenML/kitten-tts-2", DEFAULT_REVISION, "emb4", "student_w4")]


def test_the_thread_count_reaches_the_model_without_a_reload():
    engine = make_engine()
    speak(engine)
    engine.num_thread = 3
    speak(engine)
    assert engine.loads == [LOAD] and engine.made[0].calls[1]["threads"] == 3


def test_generation_changes_when_the_loaded_model_is_dropped():
    engine = make_engine()
    before = engine.generation
    asyncio.run(engine.unload())
    assert engine.generation == before + 1
