# Test it from the command line

Before the first call, open `/admin/` → **Updates** → **Download**. Startup never downloads weights. The [admin guide](guide-web-ui.md#updates-and-first-download) includes the curl alternative.

Calls Kitten2 with PowerShell only, no admin page. Port 29323. Replace `<...>` values. The commands were written from the code and not yet run against a live server.

## Get a token

Every call except `/health` needs a token while `SERVICE_ADMIN_PASSWORD` is set. Admin calls take the admin password itself; a token works only on `/v1/*`. Create one token and reuse it. Each `POST /admin/tokens` call makes a new one, so do not put it in a loop. Revoke extras on the admin page.

```powershell
$base = "http://127.0.0.1:29323"
$pw   = @{ "X-Internal-Token" = "<SERVICE_ADMIN_PASSWORD>" }
$tok  = (Invoke-RestMethod -Method Post -Uri "$base/admin/tokens" -Headers $pw -ContentType "application/json" -Body '{"name":"cli-test"}').token
$tok
$h    = @{ "X-Internal-Token" = $tok }
Invoke-RestMethod "$base/health"
```

`$pw` (the admin password) is for `/admin/*` only. `$h` (the token) is for `/v1/*` only; using the password there gives `Invalid token`. `$tok` prints once: save it to skip this step next time, then set `$h` from it. With no admin password set there is no auth: skip `-Headers $h`.

## Call it

Add a cloned voice once (admin password). The server needs a WAV file, so convert your recording first. Repeat only when the clip or transcript changes.

```powershell
$ref = "D:\User\Downloads\_temp\ref.wav"
ffmpeg -y -loglevel error -i "<recording.mp3>" -ac 1 $ref
$body = @{ audio_base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ref)); transcript = "<exactly what the recording says>" } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$base/admin/voices/myvoice" -Headers $pw -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Kitten2 also has 115 built-in voices (default `Bruno`); a built-in name cannot be replaced (409).

Speak with it. A new seed each run keeps the cache from returning old audio:

```powershell
$req = @{ text = "Hello, I hope you are having a good day."; voice = "myvoice"; seed = Get-Random -Maximum 100000 } | ConvertTo-Json
Invoke-WebRequest -Method Post -Uri "$base/v1/speak" -Headers $h -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($req)) -OutFile "D:\User\Downloads\_temp\kitten2.wav"
```

List the voices a token may use with `Invoke-RestMethod -Uri "$base/v1/voices" -Headers $h`. A token's *projects* list holds voice names: add the built-in ones you want, such as `Bruno`.

## Problems

| Answer | Cause |
|---|---|
| `401` | Wrong value: admin routes need the admin password, `/v1/*` needs a token. |
| `403` | The token's *projects* list does not include what you asked for. |
| `429` | Token rate used up or too many calls waiting; wait `Retry-After` seconds. |
| `422` | A field is unknown or out of range; the answer says which. |
| connection refused | Not running, or another port; see the run-path guides. |
