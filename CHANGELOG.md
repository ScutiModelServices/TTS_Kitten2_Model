# Changelog

## 0.1.0

- First version: KittenTTS 2 (`KittenML/kitten-tts-2`, 1.7B, 115 built-in voices, voice cloning) on the CPU through the `kittenml` package, with the admin page, tokens (scope, rate limit, expiry), metrics, Settings card, update check, answer cache and Try it panel shared with the other model services.
- `POST /v1/speak` takes `text`, `voice`, `seed`, `temperature`, `preset`, `normalize` and `stream` and returns a WAV file. `GET /v1/voices` lists built-in and cloned voices (default `Bruno`).
- Cloned voices: `PUT`/`DELETE /admin/voices/{name}` (admin password); the transcript is required, so Whisper is never loaded. A built-in name gets 409.
- Settings: `model_revision` (pinned Hub commit), `device`, `weights`, `decoder`, `max_new_tokens`.
- Measured on a Ryzen 7 7445HS: 5.7 GB resident, 6.1 GB peak, 0.1 to 0.2 times real time.
