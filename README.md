# Profilarr

[![license: MIT](https://img.shields.io/github/license/Tw1zT3d2four7/Profilarr)](LICENSE)

Profilarr is a Dispatcharr ffmpeg/cvlc hybrid stream-profile plugin. Credit goes to Seth from the Dispatcharr Dev Team for a few of the profiles used as a base for the NVIDIA options.

Every variant is a Python-supervised pipeline: a tiny `.sh` wrapper execs a shared **supervisor** process, which owns both `ffmpeg` (fetch, and — on 6 of the 7 variants — re-encode) and `cvlc` (final delivery) as real child processes for the life of the stream.

```
IPTV provider ──► ffmpeg (fetch, remux,   ──► [ NVENC or libx264   ──► cvlc (dummy output,
                   regenerate PTS)            re-encode, 6 of 7 ]      buffered delivery)   ──► Dispatcharr ──► client
                              \_______________________ owned by profilarr-supervisor.py _______________________/
```

## Why a supervisor instead of a shell pipe

A plain `ffmpeg | cvlc` shell pipeline has a real failure mode: if Dispatcharr kills the wrapper shell, the shell itself dies but `ffmpeg` and `cvlc` don't automatically get the signal — a plain `sh` script gives its pipeline children no special handling, so they're left running as orphans (reparented to PID 1) after every channel stop or switch. A `trap` in the shell script only helps if the signal is catchable (`SIGTERM`/`SIGINT`) — it does nothing against `SIGKILL`, which can't be trapped by any process, ever.

`profilarr-supervisor.py` solves this at the kernel level instead of relying on a trap:

- Each child (`ffmpeg`, `cvlc`) is launched with **`PR_SET_PDEATHSIG` set to `SIGKILL`** via `prctl()`, applied in the child's own process right before `exec`. This tells the kernel: *"if my parent process ever dies, for any reason, kill me too."*
- Because this is enforced by the kernel against the parent-child relationship itself, it works even if the supervisor is killed with an **uncatchable `SIGKILL`** — the usual trap-can't-catch-this loophole doesn't apply here, since nothing needs to run in the dying process at all.
- On a catchable signal (`SIGTERM`/`SIGINT` — what Dispatcharr normally sends on a clean channel stop), the supervisor's own handler tears both children down gracefully (`SIGTERM`, then `SIGKILL` after a 2-second grace period) before exiting.
- Each supervisor instance also writes its own PID to `/data/profilarr/run/<pid>.pid` on start and removes it on exit. The plugin's `stop()` hook globs that directory and sends `SIGTERM` to every PID found — useful for a plugin-level "stop everything" without hunting down PIDs by hand.

Net effect: no orphaned `ffmpeg`/`cvlc` processes left behind after a channel stop, switch, or even a forceful kill of the supervisor — something a shell `trap` alone cannot fully guarantee.

## The 7 profile variants

Unlike earlier versions of this plugin (multiple independently-toggleable profiles), the plugin now exposes **one dropdown** with all 7 variants; generating a profile always replaces whichever variant was previously generated under the same name prefix.

| Category | Variant | Key | What it does |
|---|---|---|---|
| Default Profile | Passthrough (base) | `passthrough` | Video passthrough, no re-encode (`-c:v copy`). Lowest CPU cost, most stable, but can still show artifacting in some players on inconsistent-timestamp or changing-frame-rate fallback streams. |
| Nvidia Encoding Options | Uncapped FPS (Nvidia) | `uncapped` | NVENC re-encode at 8Mbps CBR, source frame rate preserved (no `-vf fps=`), `-g 60 -keyint_min 60`. |
| Nvidia Encoding Options | 30 FPS Capped (Nvidia) | `fps30` | Same NVENC stage, forced to 29.97fps (`-vf fps=30000/1001 -fps_mode cfr`), `-g 60 -keyint_min 60`. |
| Nvidia Encoding Options | 60 FPS Forced (Nvidia) | `fps60` | Same NVENC stage, forced to 59.94fps (`-vf fps=60000/1001 -fps_mode cfr`), `-g 120 -keyint_min 120` (~2s GOP at the higher rate). |
| CPU Encoding Options | Uncapped FPS (CPU libx264) | `cpu_uncapped` | Software x264 re-encode at 8Mbps CBR, source frame rate preserved, `-g 60 -keyint_min 60`. |
| CPU Encoding Options | 30 FPS Capped (CPU libx264) | `cpu_fps30` | Same x264 stage, forced to 29.97fps, `-g 60 -keyint_min 60`. |
| CPU Encoding Options | 60 FPS Forced (CPU libx264) | `cpu_fps60` | Same x264 stage, forced to 59.94fps, `-g 120 -keyint_min 120`. |

All three NVENC variants share: `h264_nvenc`, preset `p4`, profile `high`, `yuv420p`, CBR at 8Mbps (`-b:v 8M -maxrate 8M -bufsize 16M`), `-sc_threshold 0`.

All three CPU variants share: `libx264`, preset `superfast`, `-tune zerolatency`, profile `high`, `yuv420p`, `-x264-params nal-hrd=cbr` to enforce true CBR in software, same 8Mbps bitrate/bufsize, `-sc_threshold 0`.

Every variant re-encodes audio to **AAC at 192kbps, stereo** (`-c:a aac -b:a 192k -ac 2 -async 1`), including passthrough — only video is ever passed through untouched.

### Adjusting bitrate or other encode settings

There are no environment-variable knobs — every setting lives directly in `profilarr-supervisor.py`'s `ffmpeg_cmd()` function, in the per-profile block for the variant you're using. Change `8M` (appears as `-b:v`, `-maxrate`) and its matching `-bufsize` (double the bitrate) there, then use the plugin's **Reinstall Scripts** action to push the change to `/data/profilarr/`. Since the supervisor is a single shared file, editing it updates every variant that uses that encode block at once — you don't need to touch each `.sh` wrapper individually (they're just thin dispatchers).

## Why the fetch/cleanup stage exists

A raw `cvlc --sout ... dst=-` pipe works most of the time, but on a provider CDN hiccup it can leave a PCR/PTS discontinuity in the output TS. Depending on the downstream player, that shows up as a freeze that only clears if you rewind — the bytes are fine, the player's demuxer just gets stuck on the bad timestamp. `ffmpeg` fetches and cleans the stream *before* `cvlc` ever sees it, so `cvlc`'s job becomes purely delivering an already-sane stream. On the six re-encode variants, the transcode happens as part of that same `ffmpeg` stage — there's no separate second ffmpeg process.

- `-user_agent` — sends the custom user-agent on ffmpeg's own HTTP request to the provider.
- `-reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5` — ffmpeg automatically retries the HTTP connection on a drop instead of stalling.
- `-multiple_requests 1 -seekable 0` — tells ffmpeg this is a live, non-seekable stream, skipping wasted range-request probing.
- `-fflags +discardcorrupt+genpts+igndts` — ignore the source's DTS and regenerate clean, monotonic PTS; discard obviously corrupt packets.
- `-map 0:v:0? -map 0:a? -sn -dn` — map the first video/audio stream if present (the `?` avoids a hard failure if one is briefly missing), explicitly drop subtitle/data streams.
- `-mpegts_copyts 1 -avoid_negative_ts disabled` — timestamps are preserved as-delivered rather than rewritten to zero, which pairs with the regenerated PTS from `genpts` above; `-muxdelay 0 -muxpreload 0` keep muxing latency minimal.
- `-max_muxing_queue_size 4096 -flush_packets 1` — enough internal buffering headroom to avoid `"Too many packets buffered"` aborts, with packets flushed immediately rather than batched.
- `-mpegts_flags +pat_pmt_at_frames+resend_headers` — PAT/PMT are repeated periodically (not just once at start) so a client that starts mid-stream or resyncs after a hiccup can do so cleanly.
- `cvlc -I dummy --no-lua --no-auto-preparse --no-dbus --no-interact --no-stats --aout adummy --vout vdummy --no-sout-all --sout-keep` — runs `cvlc` headless with no video/audio output modules, Lua, D-Bus, interactive prompts or stats overhead — it exists purely to remux and deliver.
- `--network-caching 3000 --sout-mux-caching 1500 --adaptive-logic=highest` — input-side and output-side buffering, tuned for stability over latency.
- `--sout="#std{access=file,mux=ts,dst=-}" fd://0` — reads the upstream ffmpeg's output from stdin and re-muxes it to stdout as MPEG-TS for Dispatcharr to pick up.

## Install

**Requires Dispatcharr `v0.25.0` or later.**

### Option 1 — Dispatcharr plugin (recommended)

1. **Install** the plugin: Dispatcharr → Plugins → **Find Plugins** → search `Profilarr` → Install. This copies the supervisor and generates all 7 `.sh` wrappers into `/data/profilarr/` automatically — nothing to place manually.
2. **Open** the plugin settings (Plugins → Profilarr).
3. Set **Profile Name Prefix** (default `Profilarr`) — this is the base name your generated Stream Profile will use.
4. Pick a variant from **Select Active Stream Profile Variant** — the dropdown groups all 7 by category (Default Profile / Nvidia Encoding Options / CPU Encoding Options) with a description under each.
5. Leave **Set as Systemwide Default Profile** on if you want every channel to use it without per-channel assignment, or turn it off to assign per-channel yourself.
6. Click **Apply & Synchronize Stream Profile**. You'll get a confirmation dialog first — this step is destructive by design (see below). Confirm to generate.
7. **Refresh** the Dispatcharr browser tab (the profile picker is cached client-side).

If you left "Set as default" off, assign the generated profile per-channel: Channels → Edit → **Stream Profile** → `<Profile Name Prefix> Profile (<script>.sh)`.

> **⚠️ Generating a profile deletes old ones under the same name.** Clicking **Apply & Synchronize Stream Profile** deletes *every* existing Stream Profile whose name contains your Profile Name Prefix (case-insensitive) — not just ones this plugin created — except any that are `locked`. This keeps the profile list free of stale leftover variants when you switch encode settings, but if you have an unrelated Stream Profile that happens to share the prefix text, it will be deleted too unless you lock it first or use a more distinctive prefix.

**Reinstall Scripts** (separate action, blue button) re-copies the supervisor and regenerates all 7 wrapper scripts to `/data/profilarr/` without touching your generated Stream Profile — use this after updating the plugin or if a file under `/data/profilarr/` got corrupted/deleted.

### Option 2 — Manual install (no plugin)

1. Copy `profilarr-supervisor.py` **and** whichever wrapper script(s) you want (`profilarr.sh`, `profilarr-uncapped.sh`, `profilarr-30fps-capped.sh`, `profilarr-60fps-forced.sh`, `profilarr-cpu-uncapped.sh`, `profilarr-cpu-30fps.sh`, `profilarr-cpu-60fps.sh`) into the same directory inside the Dispatcharr container's mounted `/data` volume (e.g. `/data/profilarr/`). Make the wrapper(s) executable (`chmod +x`) — the supervisor is invoked via `python3`, so it doesn't need the execute bit itself, but setting it doesn't hurt.
2. In Dispatcharr → Settings → Stream Settings → Profiles, add one entry per wrapper script you copied:

   | Field | Value |
   |---|---|
   | **Name** | e.g. `Profilarr - profilarr-60fps-forced.sh` |
   | **Command** | `/data/profilarr/profilarr-60fps-forced.sh` (or whichever wrapper) |
   | **Parameters** | `'{userAgent}' '{streamUrl}'` |
   | **Active** | yes |

3. Set one as the instance-wide default (Settings → Stream Settings → Default Stream Profile) or assign per-channel under Channels → Edit → Stream Profile.

## Requirements

`cvlc`, `ffmpeg`, and `python3` must all be installed and on `PATH` **inside the Dispatcharr container** — check with:

```bash
docker exec -it <dispatcharr-container-name> sh -c "which cvlc ffmpeg python3"
```

If any is missing, install it in whatever image/layer builds your Dispatcharr container; the wrapper will otherwise fail silently or the channel will error out on tune. The NVENC variants additionally require an NVIDIA GPU with driver support reachable from inside the container (`nvidia-smi` should work in `docker exec`).

## Troubleshooting

**Channel fails to start with a shell syntax error in the logs** (`sh: 1: Syntax error: "(" unexpected`) — this happens if the stream profile's Command/Parameters end up nested inside another shell invocation with conflicting quoting. Point **Command** directly at the wrapper script's path (not at `sh -c "..."`) and pass the two placeholders as Parameters, as shown above — Dispatcharr substitutes and splits them correctly this way.

**"Error opening input" on the provider URL, or the channel just times out** — `ffmpeg` is the one connecting straight to the provider in every profile; check the log for its own connection error (auth failure, wrong user-agent, provider down) rather than assuming it's a downstream `cvlc` issue.

**`cvlc` exits immediately with no output** — `cvlc ... fd://0` depends on the ffmpeg stage actually producing data on its stdout first. Check for an ffmpeg error in the logs; if ffmpeg never started cleanly, `cvlc` has nothing to read.

**NVENC variant fails to start, or falls back to a garbled/black picture** — confirm `nvidia-smi` works inside the container and that the container actually has GPU access (`--gpus` on `docker run`, or the equivalent `deploy.resources.reservations.devices` block in Docker Compose). A Maxwell-class GPU like a GTX 960 typically supports only 2 concurrent NVENC sessions — running more transcoded channels at once than your GPU's session limit will fail the extra ones.

**I generated a new variant and my old one is gone / a Stream Profile I didn't expect got deleted** — this is the destructive-overwrite behavior described above under Install, not a bug. Use a distinctive **Profile Name Prefix** if you keep other, unrelated Stream Profiles around, or mark any Stream Profile you want to protect as `locked`.

**Orphaned `ffmpeg`/`cvlc` processes after a channel stop** — should no longer happen as of the supervisor rewrite; each child is set up with `PR_SET_PDEATHSIG` so the kernel kills it the instant its parent (the supervisor) exits, even under `SIGKILL`. If you still see this, confirm `/data/profilarr/profilarr-supervisor.py` is actually the current version (check its `_read_installed_version()` marker or just re-run **Reinstall Scripts**) — an old wrapper that still uses a plain shell pipe won't have this protection.

## License

MIT. See [LICENSE](LICENSE).
