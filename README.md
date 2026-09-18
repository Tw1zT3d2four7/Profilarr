# Profilarr

[![license: MIT](https://img.shields.io/github/license/Tw1zT3d2four7/Profilarr)](LICENSE)

Profilarr is a Dispatcharr ffmpeg/cvlc hybrid stream-profile plugin.  "Credit goes to Seth from the Dispatcharr Dev Team for a few of the profiles I used as a Base for each option for Nvidia."

A hybrid **stream profile for [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr)**, shipped as four selectable variants. Every variant starts with the same `ffmpeg` fetch stage and ends with the same `cvlc` delivery stage; three of them insert an NVENC hardware transcode step in between.

```
IPTV provider ──► ffmpeg (fetch, remux, ──► [ NVENC re-encode, ──► cvlc (dummy output,
                   regenerate PTS)          only on 3 of the 4 ]    buffered delivery)  ──► Dispatcharr ──► client
```

## The four profiles

| # | Name shown in settings | Script | What it does |
|---|---|---|---|
| 1 | Passthrough (base) | `profilarr.sh` | `ffmpeg` fetches and remuxes, video is passed through untouched (`-c:v copy`, no re-encode) straight into `cvlc`. Lowest CPU cost, most stable, but can still show artifacting in some players on inconsistent-timestamp or changing-frame-rate fallback streams. |
| 2 | Uncapped FPS | `profilarr-uncapped.sh` | Adds an NVENC re-encode stage between fetch and `cvlc`. Source frame rate is kept as-is (no `-vf fps=`), 2-second GOPs at the source rate (`-g 60 -keyint_min 60`). The base transcode profile — start here if passthrough artifacts. |
| 3 | 30 FPS Capped | `profilarr-30fps-capped.sh` | Same NVENC stage, but forces output to 29.97fps (`-vf fps=30000/1001 -fps_mode cfr`). Higher-frame-rate sources get frames dropped to hit the cap. |
| 4 | 60 FPS Forced (With Frame Duplication) | `profilarr-60fps-forced.sh` | Same NVENC stage, forces output to 59.94fps (`-vf fps=60000/1001 -fps_mode cfr`, `-g 120 -keyint_min 120` for ~2s GOPs at the higher rate). Lower-frame-rate sources get frames **duplicated**, not motion-interpolated, so it's not CPU-harsh. |

All three NVENC variants use the same encode settings otherwise: `h264_nvenc`, preset `p4`, profile `high`, `yuv420p`, CBR at 8Mbps (`-b:v 8M -maxrate 8M -bufsize 16M`), 384kbps AAC audio, and the same corrupt-packet/timestamp/muxing/mpegts flags as the fetch stage.

### Adjusting bitrate

Edit these three values in whichever `profilarr-*.sh` you're using:

```
-b:v 8M -maxrate 8M -bufsize 16M
```

Change `8M` to the target bitrate. Keep `-b:v` and `-maxrate` equal, and set `-bufsize` to double the bitrate.

## Why this exists

A raw `cvlc --sout ... dst=-` pipe works most of the time, but on a provider CDN hiccup it can leave a PCR/PTS discontinuity in the output TS. Depending on the downstream player, that shows up as a freeze that only clears if you rewind — the bytes are fine, the player's demuxer just gets stuck on the bad timestamp. `ffmpeg` fetches and cleans the stream *before* `cvlc` ever sees it, so `cvlc`'s job becomes purely delivering an already-sane stream. On the three NVENC variants, the transcode stage sits between the two — the fetch stage still cleans up the source, `ffmpeg` then re-encodes at a fixed frame rate and bitrate, and `cvlc` still has the final word on delivery.

- `-user_agent` — sends the custom user-agent on ffmpeg's own HTTP request to the provider.
- `-reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5` — ffmpeg automatically retries the HTTP connection on a drop instead of stalling.
- `-multiple_requests 1 -seekable 0` — tells ffmpeg this is a live, non-seekable stream, skipping wasted range-request probing.
- `-fflags +genpts+igndts+discardcorrupt` — ignore the source's DTS and regenerate clean, monotonic PTS; discard obviously corrupt packets.
- `-c:v copy` (fetch stage) — video is passed through untouched here; re-encoding, if any, happens later in the pipeline.
- `-c:a aac -b:a 128k -ac 2 -async 1` — fetch-stage audio is re-encoded to a normalized AAC stereo stream and re-synced, in case the source audio is malformed or the channel layout is inconsistent.
- `-avoid_negative_ts make_zero` — any negative timestamp produced by a discontinuity gets clamped to zero instead of propagating.
- `-mpegts_flags +resend_headers+pat_pmt_at_frames+initial_discontinuity` — PAT/PMT are repeated periodically (not just once at start) so a client that starts mid-stream or resyncs after a hiccup can do so cleanly, and the very start of the output is honestly flagged as a discontinuity.
- **NVENC stage (variants 2-4 only)** — re-reads the already-cleaned stream from `pipe:0`, applies `-fflags +discardcorrupt+genpts` again as a second pass, optionally forces a constant frame rate with `-vf fps=... -fps_mode cfr`, and re-encodes video with `h264_nvenc` at a fixed CBR bitrate while re-encoding audio to 384kbps AAC.
- `cvlc -I dummy --no-lua --no-auto-preparse --no-dbus --no-interact --no-stats --aout adummy --vout vdummy --no-sout-all --sout-keep` — runs `cvlc` headless with no video/audio output modules, Lua, D-Bus, interactive prompts or stats overhead — it exists purely to remux and deliver.
- `--network-caching 3000 --sout-mux-caching 1500 --adaptive-logic=highest` — input-side and output-side buffering, tuned for stability over latency.
- `--sout="#std{access=file,mux=ts,dst=-}" fd://0` — reads the upstream ffmpeg's output from stdin and re-muxes it to stdout as MPEG-TS for Dispatcharr to pick up.

## Install

### Option 1 — Dispatcharr plugin (recommended, once listed in the official directory)

1. **Install** the plugin: Dispatcharr → Plugins → **Find Plugins** → search `Profilarr` → Install.
2. **Open** the plugin settings (Plugins → Profilarr).
3. **Enable** whichever of the four profiles you want (Passthrough is on by default). Each toggle shows the script filename right in its label, e.g. *Enable 'Uncapped FPS' (profilarr-uncapped.sh)*.
4. **(Optional)** tick **exactly one** "Set as default Stream Profile" toggle among the profiles you enabled, if you want every channel to use it without per-channel assignment. Ticking more than one returns an error instead of guessing.
5. Click **Generate Stream Profiles**. One Stream Profile per enabled variant appears in Settings → Stream Settings → Profiles, named `<Profile Name> - <script filename>.sh` — the name always tells you exactly which script it runs.
6. **Refresh** the Dispatcharr browser tab (the profile picker is cached client-side).

If you didn't set a default in step 4, assign a profile per-channel: Channels → Edit → **Stream Profile** → pick one of the four.

### Option 2 — Manual install (no plugin)

1. Put all four `profilarr*.sh` scripts inside the Dispatcharr container's mounted `/data` volume (e.g. `/data/profilarr/`). Make each executable (`chmod +x`).
2. In Dispatcharr → Settings → Stream Settings → Profiles, add one entry per script you want to use:

   | Field | Value |
   |---|---|
   | **Name** | e.g. `Profilarr - profilarr-60fps-forced.sh` |
   | **Command** | `/data/profilarr/profilarr-60fps-forced.sh` (or whichever script) |
   | **Parameters** | `'{userAgent}' '{streamUrl}'` |
   | **Active** | yes |

3. Set one as the instance-wide default (Settings → Stream Settings → Default Stream Profile) or assign per-channel under Channels → Edit → Stream Profile.

## Requirements

Both `cvlc` and `ffmpeg` must be installed and on `PATH` **inside the Dispatcharr container** — check with:

```bash
docker exec -it <dispatcharr-container-name> which cvlc ffmpeg
```

If either is missing, install it in whatever image/layer builds your Dispatcharr container; the script will otherwise fail silently or the channel will error out on tune. The NVENC variants additionally require an NVIDIA GPU with driver support reachable from inside the container (`nvidia-smi` should work in `docker exec`).

## Tuning

There are no environment-variable knobs. Every setting (`--network-caching`, ffmpeg flags, audio bitrate, video bitrate, GOP size, etc.) is hardcoded directly in the relevant `profilarr*.sh`. To change behavior, edit the script and, if installed via the plugin, use the **Reinstall scripts** action to push the change to `/data/profilarr/`.

Each script takes two **positional** arguments — `$1` is the user-agent, `$2` is the stream URL — matching the `'{userAgent}' '{streamUrl}'` order in Parameters above. None of them parse named flags; if you need to change the argument order, update both the Parameters field and the `$1`/`$2` references in the script together.

## Troubleshooting

**Channel fails to start with a shell syntax error in the logs** (`sh: 1: Syntax error: "(" unexpected`) — this happens if the stream profile's Command/Parameters end up nested inside another shell invocation with conflicting quoting. Point **Command** directly at the script's path (not at `sh -c "..."`) and pass the two placeholders as Parameters, as shown above — Dispatcharr substitutes and splits them correctly this way.

**"Error opening input" on the provider URL, or the channel just times out** — `ffmpeg` is the one connecting straight to the provider in every profile; check the log for its own connection error (auth failure, wrong user-agent, provider down) rather than assuming it's a downstream `cvlc` issue.

**`cvlc` exits immediately with no output** — `cvlc ... fd://0` depends on whatever ffmpeg stage precedes it actually producing data on its stdout first. Check for an ffmpeg error just above this line; if ffmpeg never started cleanly (see the syntax-error case above), `cvlc` has nothing to read.

**NVENC variant fails to start, or falls back to a garbled/black picture** — confirm `nvidia-smi` works inside the container and that the container actually has GPU access (`--gpus` on `docker run`, or the equivalent `deploy.resources.reservations.devices` block in Docker Compose). A Maxwell-class GPU like a GTX 960 typically supports only 2 concurrent NVENC sessions — running more transcoded channels at once than your GPU's session limit will fail the extra ones.

**Only one profile ever gets set as default** — the plugin errors out on **Generate Stream Profiles** if more than one "Set as default" toggle is ticked at once, rather than silently picking one. Untick all but one and re-run.

## License

MIT. See [LICENSE](LICENSE).
