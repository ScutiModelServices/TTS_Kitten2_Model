# Purpose

**Kind:** text (+ optional reference clip) → audio

**Group:** Text-to-Speech

**Tags:** `cpu`, `streaming`, `voice-cloning`, `multilingual`, `license-restricted`

| | |
|---|---|
| Input | Text, voice name (115 built-in voices, 16 languages), seed, temperature, preset. To add a cloned voice: a WAV clip plus its transcript (admin `PUT /admin/voices/{name}`). |
| Output | WAV file (16-bit mono, 24 kHz). |
| Runs on | CPU by default (heavy, 1.7B params). |

**Use for:** multilingual speech with many voices, and zero-shot voice cloning without a GPU.
**Not for:** low latency on CPU. Licence limits commercial use above USD 1M revenue or funding.
