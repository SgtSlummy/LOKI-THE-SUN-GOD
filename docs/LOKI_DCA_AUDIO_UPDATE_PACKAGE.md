# LOKI DCA / High-Fidelity Audio Update Package

> For Hermes: implement with the `subagent-driven-development` skill task-by-task, then verify with the live Discord voice checklist from `discord-bot-voice-music-ops`.

Goal: add a safe, production-ready high-fidelity audio package to LOKI that improves voice/music reliability, supports pre-encoded Discord Audio assets, expands codec diagnostics, and clearly separates Discord-bot-safe server audio from client-patcher experiments.

Architecture: keep Lavalink/Wavelink as the primary live music transport because LOKI is a Python Discord bot already deployed with Lavalink v4 and Wavelink. Add an optional DCA asset pipeline for short pre-encoded Opus soundboard/alert clips and diagnostics, not as a replacement for Lavalink streaming. Add codec intake/transcoding tools around FFmpeg for uploads and local files. Treat client patchers such as Disctreo / Discord Experimental Subsystem as operator research only; do not install, download, or distribute patched Discord client binaries from LOKI.

Tech stack: Python 3.11, discord.py 2.7, Wavelink >=3.4,<4, Lavalink 4.2, FFmpeg, optional Go-built `dca` CLI for Discord Audio file generation, pytest, Railway.

Date researched: 2026-05-13

---

## Source Findings

### Discord Audio DCA sources

1. `jonas747/dca` now resolves through GitHub as `jogramming/dca`.
   - Go implementation for Discord Audio format.
   - Implements DCA v0/v1 encoder, decoder, and streamer helpers.
   - CLI creates DCA files from standard audio files or stdin.
   - Key defaults/claims from README and CLI source:
     - stereo audio
     - 48 kHz sample rate
     - Opus frames
     - 20 ms default frame duration
     - bitrate range intended for Discord-style output, typically 8-128 kbps
     - CLI flags include `-i`, `-ac`, `-ar`, `-as`, `-ab`, `-aa`, `-vbr`, `-raw`, `-vol`, `-threads`, `-quiet`
   - Practical use for LOKI: offline pre-encoded Opus/DCA assets and validation fixtures.
   - Avoid using it to replace Lavalink for normal streaming; LOKI is Python and Lavalink already owns queue/search/live playback.

2. `liclac/dca`
   - C Discord Audio encoder.
   - Wraps FFmpeg, can be used as CLI/library.
   - README shows DCA 0 encoding is implemented; DCA 1 and richer metadata headers were incomplete in the repo snapshot.
   - Last pushed in 2016.
   - Practical use for LOKI: research/reference only, not the default runtime dependency.

3. CuratedGo DCA URL
   - The supplied CuratedGo URL currently resolves to a domain-sale page, not useful technical documentation.
   - Do not build any package step that depends on this page being available.

### Codec references

4. Transloadit audio codec matrix
   - Confirms FFmpeg stack support for Opus: decoders `opus`, `libopus`; encoders `opus`, `libopus`.
   - Confirms FFmpeg stack support for DTS / DCA Coherent Acoustics: codec name `dts`, description `DCA (DTS Coherent Acoustics)`, decoder `dca`, encoder `dca`.
   - Important naming collision: DTS/DCA is not Discord Audio DCA. LOKI docs and code must use explicit labels:
     - `discord_dca` for Discord Audio container/frames.
     - `dts_dca` for DTS Coherent Acoustics codec.

5. VideoHelp / audio-digital DTS encoder references
   - Useful for understanding FFmpeg DTS multi-channel encoding, but Discord voice playback does not transmit DTS. Discord voice expects Opus-style voice packets at 48 kHz.
   - Practical use for LOKI: accept/upload/transcode DTS source material into Opus/PCM preview assets; never advertise DTS as directly playable through Discord voice.

### Client audio patcher references

6. `Kamar-Musik-Studio/inject-discord-stereo`
   - README describes Disctreo: patches local Discord client files for high bitrate, stereo, lossless/raw voice processing.
   - It modifies Discord client binaries/modules and includes risk disclaimers.
   - Practical use for LOKI: inspiration for an operator-facing “high quality setup guide” and a red/yellow/green compatibility warning. Do not automate patching Discord clients from LOKI.

7. `UnpackedX/Discord-Experimental-Subsystem`
   - Codeberg repo describes high-fidelity Discord voice module replacement/config guidance.
   - README instructs replacing `discord_voice.node`, `index.js`, optional `experimental.node`, and changing Discord voice settings.
   - Practical use for LOKI: operator research/reference only. Do not ship patched native modules in the bot package.

---

## Package Name

`loki-audio-dca-hifi-pack`

## What This Package Adds

### 0. High-quality audio intake for every input

Purpose: every audio input path LOKI accepts should pass through one consistent high-quality intake policy before playback, queueing, clipping, previewing, transcription, archiving, or DCA asset generation. The policy should preserve the best available source until the final Discord-compatible output step, then encode once to the appropriate target.

Input paths covered:
- Discord natural-language requests: `play ...`, `queue ...`, music requests routed through `cogs/loki_npc.py`.
- Slash/hybrid commands: `/play`, `/queue`, `/grab`, `/lyrics`, future `/clip`, `/soundboard`, `/import-audio`.
- Spotify links: use Spotify as metadata only; resolve to the highest-quality permitted playable source. Do not claim lossless Spotify.
- YouTube / YouTube Music / SoundCloud / other Lavalink sources: prefer source order and Lavalink plugins that return stable, high-quality streams; avoid extra bot-side transcoding.
- Local operator files: WAV, FLAC, AIFF, ALAC, MP3, AAC, Opus, Ogg, WebM, DTS/DCA source material, and other FFmpeg-readable files.
- Discord attachments: only after admin/operator policy allows them; probe first, size/duration limit second, then transcode or reject.
- Generated audio: TTS, AI music, sound effects, video-extracted audio, and future local model outputs.
- Short LOKI assets: intros, alerts, buttons, soundboard clips, and DCA fixtures.
- Voice-related inputs: voice-channel recordings/transcripts if later enabled; keep them separate from music playback and respect consent/privacy gates.

Quality policy:
- Keep source media untouched in a cache/archive when allowed by policy.
- Probe with FFmpeg/ffprobe before transcoding when the input is local or attached media.
- Normalize target output to Discord-safe Opus: 48 kHz, stereo when useful, 20 ms frames, clean gain staging, no clipping.
- Use a loudness target for generated/local media, recommended `-16 LUFS` integrated with true peak no higher than `-1.5 dBTP`, unless the source is already mastered and operator chooses passthrough.
- Preserve stereo for music and effects. Downmix multichannel sources with a predictable pan/downmix rule and record the decision in metadata.
- Prefer one final encode. Do not decode/re-encode repeatedly across queue, preview, clip, and playback paths.
- For live remote playback, let Lavalink do the streaming path and use EQ/volume controls rather than pre-transcoding in the bot.
- For local clips/assets, create high-quality Opus or Discord Audio DCA derivatives from the original source and keep metadata sidecars.

New module:
- Create: `loki_music/audio_intake.py`
- Test: `tests/test_loki_audio_intake.py`

Suggested API:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AudioInputKind(str, Enum):
    REMOTE_LAVALINK = "remote_lavalink"
    SPOTIFY_METADATA = "spotify_metadata"
    LOCAL_FILE = "local_file"
    DISCORD_ATTACHMENT = "discord_attachment"
    GENERATED_AUDIO = "generated_audio"
    DCA_ASSET = "dca_asset"
    VOICE_CAPTURE = "voice_capture"


@dataclass(frozen=True)
class HighQualityAudioProfile:
    sample_rate_hz: int = 48000
    channels: int = 2
    frame_ms: int = 20
    codec: str = "opus"
    nominal_bitrate_kbps: int = 128
    loudness_lufs: float = -16.0
    true_peak_db: float = -1.5
    preserve_original: bool = True


@dataclass(frozen=True)
class AudioIntakeDecision:
    kind: AudioInputKind
    source_label: str
    profile: HighQualityAudioProfile
    route: str
    requires_probe: bool
    requires_transcode: bool
    warnings: tuple[str, ...] = ()


def decide_audio_intake(source: str, kind: AudioInputKind) -> AudioIntakeDecision:
    if kind == AudioInputKind.SPOTIFY_METADATA:
        return AudioIntakeDecision(
            kind=kind,
            source_label=source,
            profile=HighQualityAudioProfile(),
            route="resolve_metadata_then_lavalink_search",
            requires_probe=False,
            requires_transcode=False,
            warnings=("Spotify links provide metadata/search context only; LOKI must not advertise lossless Spotify playback.",),
        )
    if kind == AudioInputKind.REMOTE_LAVALINK:
        return AudioIntakeDecision(kind, source, HighQualityAudioProfile(), "lavalink_direct", False, False)
    if kind in {AudioInputKind.LOCAL_FILE, AudioInputKind.DISCORD_ATTACHMENT, AudioInputKind.GENERATED_AUDIO}:
        return AudioIntakeDecision(kind, source, HighQualityAudioProfile(), "ffprobe_then_discord_opus", True, True)
    if kind == AudioInputKind.DCA_ASSET:
        return AudioIntakeDecision(kind, source, HighQualityAudioProfile(), "validate_dca_then_clip_backend", True, False)
    return AudioIntakeDecision(kind, source, HighQualityAudioProfile(), "operator_review_required", True, True)
```

Acceptance:
- Every new audio entrypoint must call the intake decision layer or document why Lavalink already owns the route.
- Spotify requests must include the “metadata/search only, not lossless Spotify” warning in operator docs/status when relevant.
- Local/attachment/generated audio must be probed and policy-checked before FFmpeg/DCA work.
- Unit tests cover all `AudioInputKind` values.

### 1. Audio capability registry

Create a single source of truth for LOKI audio capabilities.

Files:
- Create: `loki_music/audio_capabilities.py`
- Test: `tests/test_loki_audio_capabilities.py`

Core API:

```python
from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioToolStatus:
    name: str
    present: bool
    path: str | None = None
    purpose: str = ""


@dataclass(frozen=True)
class AudioCapabilitySnapshot:
    ffmpeg: AudioToolStatus
    dca: AudioToolStatus
    supports_discord_dca_assets: bool
    supports_dts_input_transcode: bool
    warnings: tuple[str, ...]


def audio_capabilities() -> AudioCapabilitySnapshot:
    ffmpeg_path = shutil.which("ffmpeg")
    dca_path = shutil.which("dca")
    warnings: list[str] = []
    if dca_path is None:
        warnings.append("Optional Discord Audio DCA CLI is not installed; pre-encoded DCA asset generation is disabled.")
    if ffmpeg_path is None:
        warnings.append("FFmpeg is not installed; codec probing/transcoding is disabled.")
    return AudioCapabilitySnapshot(
        ffmpeg=AudioToolStatus("ffmpeg", ffmpeg_path is not None, ffmpeg_path, "probe/transcode source media"),
        dca=AudioToolStatus("dca", dca_path is not None, dca_path, "generate Discord Audio DCA/Opus assets"),
        supports_discord_dca_assets=dca_path is not None,
        supports_dts_input_transcode=ffmpeg_path is not None,
        warnings=tuple(warnings),
    )
```

Acceptance:
- Report tool presence without printing secrets.
- Use precise names: Discord Audio DCA vs DTS/DCA.
- Does not fail if optional `dca` is missing.

### 2. Codec vocabulary and guardrails

Files:
- Create: `loki_music/codec_policy.py`
- Test: `tests/test_loki_codec_policy.py`

Rules:
- `discord_dca`: Discord Audio pre-encoded Opus-frame file/container.
- `dts_dca`: DTS Coherent Acoustics, FFmpeg codec `dca` under `dts`.
- Discord voice output target remains: Opus, 48 kHz, 1-2 channels, normal Discord-compatible bitrate.
- Uploaded DTS/multichannel content may be accepted as source material, then downmixed/transcoded for Discord.
- Never claim Discord voice can transmit DTS/lossless client-patched audio from the bot.

Suggested API:

```python
DISCORD_VOICE_TARGET = {
    "codec": "opus",
    "sample_rate_hz": 48000,
    "channels": 2,
    "frame_ms": 20,
    "max_nominal_bitrate_kbps": 128,
}

CODEC_ALIASES = {
    "discord_dca": "Discord Audio container/Opus frame stream",
    "dts_dca": "DTS Coherent Acoustics codec; FFmpeg codec name dca under dts",
}


def explain_codec(term: str) -> str:
    normalized = term.strip().lower().replace("-", "_")
    if normalized in {"dca", "discord_audio", "discord_dca"}:
        return CODEC_ALIASES["discord_dca"]
    if normalized in {"dts", "dts_dca", "coherent_acoustics"}:
        return CODEC_ALIASES["dts_dca"]
    return "Unknown or unsupported codec term."
```

### 3. Optional DCA asset builder

Purpose: create pre-encoded Discord Audio clips for short LOKI alerts, intros, server soundboard clips, and test fixtures.

Files:
- Create: `loki_music/dca_assets.py`
- Create: `scripts/build_dca_asset.py`
- Test: `tests/test_loki_dca_assets.py`

Behavior:
- Input: local audio file path.
- Output: `.dca` asset under `data/audio_assets/` or configured cache dir.
- Calls `dca` CLI only if installed.
- Default encode profile:
  - channels: 2
  - sample rate: 48000
  - frame duration: 20 ms
  - bitrate: 128 kbps for music/alerts, configurable down to 64 kbps
  - application: audio
  - quiet mode enabled
- Never shells through unsanitized strings; use `subprocess.run([...])`.
- Records JSON sidecar metadata for source path, profile, duration if probed, and created timestamp.

Example command implementation:

```python
cmd = [
    dca_path,
    "-i", str(input_path),
    "-ac", "2",
    "-ar", "48000",
    "-as", "20",
    "-ab", str(bitrate_kbps),
    "-aa", "audio",
    "-quiet",
]
```

Note: the historical CLI writes to stdout. The script should open the output file in binary mode and use `stdout=out_file`.

Acceptance:
- If `dca` missing, return a clear operator error and do not crash bot startup.
- Unit tests mock `shutil.which` and `subprocess.run`.
- DCA generation is local/offline only unless explicitly called by an admin/operator command.

### 4. Discord Audio DCA reader/validator for Python

Purpose: allow LOKI to inspect generated `.dca` assets and verify they contain sane length-prefixed Opus frames before playback experiments.

Files:
- Create: `loki_music/dca_format.py`
- Test: `tests/test_loki_dca_format.py`

Implementation concept:
- Read little-endian signed/unsigned 16-bit frame length followed by frame bytes, matching the Go `DecodeFrame` idea.
- Reject negative frame sizes, zero-length endless loops, truncated frames, and files over configured limits.
- Expose `iter_dca_frames(path)` and `inspect_dca(path)`.

Do not build live playback on this until validator tests pass.

### 5. Optional local Discord voice fallback for pre-encoded clips

Purpose: play short local clips when Lavalink is down or when LOKI needs an intro/alert effect.

Files:
- Modify: `loki_music/wavelink_backend.py`
- Create: `loki_music/local_voice_backend.py`
- Test: `tests/test_loki_local_voice_backend.py`

Design:
- Keep `WavelinkBackend` as primary.
- Add `LocalVoiceClipBackend` for operator-approved local files only.
- Use discord.py voice client and an AudioSource strategy:
  - Phase 1: use `discord.FFmpegOpusAudio` for supported local files if FFmpeg exists.
  - Phase 2 experimental: use a custom `DcaOpusAudioSource` only after validating `is_opus()` and frame timing behavior against discord.py expectations.
- Never route public arbitrary URLs through local FFmpeg in production; use Lavalink for remote media.

Guardrails:
- Max clip length default: 30 seconds.
- Max file size default: 20 MB.
- Admin-only or local-operator-only.
- No automatic download from untrusted links.

### 6. FFmpeg codec probe/transcode helper

Files:
- Create: `loki_music/ffmpeg_tools.py`
- Create: `scripts/probe_audio_codec.py`
- Test: `tests/test_loki_ffmpeg_tools.py`

Behavior:
- `ffprobe_audio(path)` returns codec name, channels, sample rate, duration.
- `transcode_for_discord_preview(path, out_path)` produces Opus target suitable for Discord preview.
- Detect DTS/DCA sources and report:
  - source is DTS Coherent Acoustics, not Discord Audio DCA.
  - output will be Opus 48 kHz stereo for Discord.

Commands should use argument lists, not shell strings.

### 7. Operator-facing audio status in dashboard/Hermes

Files:
- Modify: `utils/operator_surface.py`
- Modify: `docs/PROCESS_AND_CONNECTIONS.md`
- Test: `tests/test_operator_surface_audio.py`

Expose:
- Lavalink status: configured/connected/search OK if known.
- Discord voice dependencies: Wavelink, PyNaCl, davey.
- FFmpeg presence.
- Optional DCA CLI presence.
- Warning if client-patcher references are requested: “not installed by LOKI; manual operator research only.”

### 8. Documentation pack

Files:
- Create: `docs/AUDIO_DCA_AND_HIFI.md`
- Modify: `docs/RAILWAY_DEPLOYMENT.md`
- Modify: `docs/QUALITY_GATES.md`

Content requirements:
- Explain Discord Audio DCA vs DTS/DCA.
- Explain why LOKI keeps Lavalink for streaming.
- Explain optional DCA asset build flow.
- Explain client patcher risk and why LOKI will not automate it.
- Add Railway note: `dca` CLI and FFmpeg may not exist in production image unless explicitly installed; do not make worker startup depend on optional DCA.

---

## Explicit Non-Goals

- Do not replace Lavalink/Wavelink music playback with DCA.
- Do not ship patched Discord client modules.
- Do not bypass Discord account/client restrictions from the bot.
- Do not promise lossless Discord bot voice; Discord bot voice path remains Opus-compatible.
- Do not treat DTS/DCA codec material as Discord Audio DCA.

---

## Implementation Plan

### Task 0: Add high-quality audio intake policy

Objective: make every audio input path choose a safe high-quality route before playback, transcoding, clipping, previewing, or DCA generation.

Files:
- Create: `loki_music/audio_intake.py`
- Create: `tests/test_loki_audio_intake.py`

Steps:
1. Write tests for each `AudioInputKind`: remote Lavalink, Spotify metadata, local file, Discord attachment, generated audio, DCA asset, and voice capture.
2. Assert Spotify routes to metadata/search only and warns that lossless Spotify is not supported.
3. Assert local/attachment/generated inputs require ffprobe and transcode to the high-quality Discord Opus profile.
4. Implement `HighQualityAudioProfile`, `AudioIntakeDecision`, and `decide_audio_intake()`.
5. Run: `TMPDIR=/tmp PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/Scripts/python.exe -m pytest -q tests/test_loki_audio_intake.py`
6. Commit: `feat: add high-quality audio intake policy`.

### Task 1: Add codec vocabulary tests

Objective: lock down the DCA naming collision before code is added.

Files:
- Create: `tests/test_loki_codec_policy.py`
- Create: `loki_music/codec_policy.py`

Steps:
1. Write tests for `explain_codec("dca")`, `explain_codec("dts")`, and `DISCORD_VOICE_TARGET`.
2. Run: `TMPDIR=/tmp PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/Scripts/python.exe -m pytest -q tests/test_loki_codec_policy.py`
3. Implement `codec_policy.py`.
4. Re-run the test.
5. Commit: `feat: add LOKI audio codec policy`.

### Task 2: Add audio capability registry

Objective: detect FFmpeg and optional `dca` safely.

Files:
- Create: `loki_music/audio_capabilities.py`
- Create: `tests/test_loki_audio_capabilities.py`

Steps:
1. Mock `shutil.which` to test present/missing states.
2. Add dataclasses and `audio_capabilities()`.
3. Verify missing `dca` only warns.
4. Run targeted test.
5. Commit: `feat: add audio capability registry`.

### Task 3: Add DCA asset builder

Objective: let operators pre-encode short local clips without affecting bot startup.

Files:
- Create: `loki_music/dca_assets.py`
- Create: `scripts/build_dca_asset.py`
- Create: `tests/test_loki_dca_assets.py`

Steps:
1. Test command construction with mocked `subprocess.run`.
2. Test missing CLI returns operator error.
3. Implement sanitized command invocation.
4. Add script arg parser: `input`, `--output`, `--bitrate`.
5. Run targeted test.
6. Commit: `feat: add optional DCA asset builder`.

### Task 4: Add DCA frame inspector

Objective: validate `.dca` assets before any playback experiment.

Files:
- Create: `loki_music/dca_format.py`
- Create: `tests/test_loki_dca_format.py`

Steps:
1. Test valid length-prefixed frame parsing.
2. Test truncated frame rejection.
3. Test negative/oversize frame rejection.
4. Implement parser with strict limits.
5. Run targeted test.
6. Commit: `feat: inspect Discord Audio DCA assets`.

### Task 5: Add FFmpeg probe/transcode helpers

Objective: support codec intake and DTS/DCA source detection.

Files:
- Create: `loki_music/ffmpeg_tools.py`
- Create: `scripts/probe_audio_codec.py`
- Create: `tests/test_loki_ffmpeg_tools.py`

Steps:
1. Mock `ffprobe` JSON output for Opus and DTS/DCA.
2. Test that DTS/DCA is labelled as `dts_dca`.
3. Implement `ffprobe_audio()` and `transcode_for_discord_preview()` command builders.
4. Run targeted test.
5. Commit: `feat: add FFmpeg audio probe tools`.

### Task 6: Add operator status integration

Objective: make Hermes/dashboard show audio readiness clearly.

Files:
- Modify: `utils/operator_surface.py`
- Create/modify tests: `tests/test_operator_surface_audio.py` or existing operator surface tests.

Steps:
1. Add test expecting FFmpeg/DCA optional status fields.
2. Update operator snapshot to include audio capabilities.
3. Ensure secrets are not included.
4. Run targeted test.
5. Commit: `feat: expose LOKI audio capability status`.

### Task 7: Add local voice clip backend behind admin/operator gate

Objective: allow short local pre-encoded/FFmpeg-opus clips without weakening the Lavalink path.

Files:
- Create: `loki_music/local_voice_backend.py`
- Modify: `cogs/loki_music.py` only if adding a command/control surface.
- Create: `tests/test_loki_local_voice_backend.py`

Steps:
1. Test file size/extension/duration guardrails.
2. Test non-admin/public arbitrary URL is rejected.
3. Implement `LocalVoiceClipBackend` with `FFmpegOpusAudio` first.
4. Leave DCA direct source behind an experimental flag: `LOKI_ENABLE_DCA_CLIP_SOURCE=false` by default.
5. Run targeted test.
6. Commit: `feat: add guarded local voice clip backend`.

### Task 8: Add docs and deployment notes

Objective: make the package installable and understandable.

Files:
- Create: `docs/AUDIO_DCA_AND_HIFI.md`
- Modify: `docs/RAILWAY_DEPLOYMENT.md`
- Modify: `docs/QUALITY_GATES.md`

Steps:
1. Document source findings and non-goals.
2. Document local tool installation options.
3. Document Railway optional dependency behavior.
4. Document verification checklist.
5. Commit: `docs: add DCA and high-fidelity audio guide`.

---

## Verification Gates

Local repository gates:

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe scripts/secret_scan.py
TMPDIR=/tmp PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/release_check.py
```

Activity bridge gates if touched:

```bash
cd services/activity-bridge
npm run typecheck
npm run build
```

Production audio verification after deployment:

1. Railway worker is online.
2. Worker logs show `loki_music` loaded.
3. Worker logs do not show `voice will NOT be supported`.
4. Lavalink `/version` returns 200.
5. Lavalink `/v4/loadtracks` returns search results.
6. Operator status shows FFmpeg, optional DCA status, and high-quality intake policy without secrets.
7. Each input class has a verified route: remote Lavalink, Spotify metadata, local file, Discord attachment, generated audio, DCA asset, and voice capture/operator-review.
8. Spotify links are reported as metadata/search only, not lossless Spotify.
9. A human joins a Discord voice channel.
10. LOKI plays a normal Lavalink track audibly.
11. If enabled, LOKI plays a short local operator-approved clip audibly.
12. If DTS/DCA source file is tested, LOKI labels it as DTS/DCA input and transcodes to Discord Opus target.

---

## Risk Register

1. DCA name collision causes wrong implementation.
   - Mitigation: `codec_policy.py` and docs use `discord_dca` vs `dts_dca`.

2. Optional DCA CLI breaks production startup.
   - Mitigation: detect at runtime, warn only, no import-time failure.

3. “Every input” high-quality handling creates unsafe upload/download paths.
   - Mitigation: all non-Lavalink media must pass `audio_intake.py`, ffprobe, size/duration limits, admin/operator gates, and local-file-only rules before transcoding.

4. Client patcher references encourage unsafe automation.
   - Mitigation: docs mark these as manual operator research only; bot never downloads or applies patched Discord client modules.

5. Local FFmpeg path becomes an SSRF/remote download vector.
   - Mitigation: local files only, no public URL ingestion, admin/operator gate, max size/duration.

6. Discord audible playback still unproven.
   - Mitigation: keep physical Discord voice test as release gate.

7. YouTube source failures continue for some tracks.
   - Mitigation: keep current source fallback order: SoundCloud, YouTube Music, YouTube; expose failures in operator status.

---

## Recommended First Build Slice

Build Task 0 first so every future audio feature uses the same high-quality intake policy. Then build Tasks 1-4 for safe vocabulary, status detection, optional DCA asset generation, and `.dca` validation without changing live production playback. After those pass, build Tasks 5-8 for transcoding, operator status, local clip playback, and docs.
