# Profilarr

[![license: MIT](https://img.shields.io/github/license/Tw1zT3d2four7/Profilarr)](LICENSE)

A hybrid **stream profile for [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr)**: `cvlc` pulls and demuxes the provider stream, `ffmpeg` remuxes it and regenerates timestamps before Dispatcharr's proxy hands it to clients.

```
IPTV provider  ──►  cvlc (fetch, demux,   ──►  ffmpeg (remux,         ──►  Dispatcharr  ──►  client
                     custom user-agent,        regenerate PTS,
                     network-caching)           resend PAT/PMT)
```

## Why this exists

A raw `cvlc --sout ... dst=-` pipe works most of the time, but on a provider CDN hiccup it can leave a PCR/PTS discontinuity in the output TS. Depending on the downstream player, that shows up as a freeze that only clears if you rewind — the bytes are fine, the player's demuxer just gets stuck on the bad timestamp. `ffmpeg` sits between `cvlc` and Dispatcharr to normalize that:

- `-fflags +genpts+igndts` — ignore the source's DTS and regenerate clean, monotonic PTS.
- `-c:v copy` — video is passed through untouched (no re-encode, no quality loss, minimal CPU).
- `-c:a aac -b:a 128k -ac 2 -async 1` — audio is re-encoded to a normalized AAC stereo stream and re-synced against video, in case the source audio is malformed or the channel layout is inconsistent.
- `-avoid_negative_ts make_zero` — any negative timestamp produced by a discontinuity gets clamped to zero instead of propagating.
- `-mpegts_flags +resend_headers+pat_pmt_at_frames+initial_discontinuity` — PAT/PMT are repeated periodically (not just once at start) so a client that starts mid-stream or resyncs after a hiccup can do so cleanly, and the very start of the output is honestly flagged as a discontinuity.

## Install

### Option 1 — Dispatcharr plugin (recommended, once listed in the official directory)

1. **Install** the plugin: Dispatcharr → Plugins → **Find Plugins** → search `Profilarr` → Install.
2. **Open** the plugin settings (Plugins → Profilarr).
3. **(Optional)** tick **"Set as default Stream Profile"** if you want every channel to use it without per-channel assignment.
4. Click **Generate Stream Profile**. A profile named `Profilarr` appears in Settings → Stream Settings → Profiles.
5. **Refresh** the Dispatcharr browser tab (the profile picker is cached client-side).

If you didn't set it as default in step 3, assign it per-channel: Channels → Edit → **Stream Profile** → `Profilarr`.

### Option 2 — Manual install (no plugin)

1. Put `profilarr.sh` inside the Dispatcharr container's mounted `/data` volume (e.g. `/data/profilarr/profilarr.sh`). Make it executable (`chmod +x`).
2. In Dispatcharr → Settings → Stream Settings → Profiles, add:

   | Field | Value |
   |---|---|
   | **Name** | `Profilarr` |
   | **Command** | `/data/profilarr/profilarr.sh` |
   | **Parameters** | `-ua {userAgent} -i {streamUrl}` |
   | **Active** | yes |

3. Set it as the instance-wide default (Settings → Stream Settings → Default Stream Profile) or per-channel under Channels → Edit → Stream Profile.

## Requirements

Both `cvlc` and `ffmpeg` must be installed and on `PATH` **inside the Dispatcharr container** — check with:

```bash
docker exec -it <dispatcharr-container-name> which cvlc ffmpeg
```

If either is missing, install it in whatever image/layer builds your Dispatcharr container; the script will otherwise fail silently or the channel will error out on tune.

## Tuning

There are no environment-variable knobs. Every setting (`--network-caching`, ffmpeg flags, audio bitrate, etc.) is hardcoded directly in `profilarr.sh`. To change behavior, edit the script and, if installed via the plugin, use the **Reinstall script** action to push the change to `/data/profilarr/`.

The script takes two **positional** arguments — `$1` is the user-agent, `$2` is the stream URL — matching the `-ua {userAgent} -i {streamUrl} ` order in Parameters above. It does not parse named flags; if you need to change the argument order, update both the Parameters field and the `$1`/`$2` references in the script together.

## Troubleshooting

**Channel fails to start with a shell syntax error in the logs** (`sh: 1: Syntax error: "(" unexpected`) — this happens if the stream profile's Command/Parameters end up nested inside another shell invocation with conflicting quoting. Point **Command** directly at the script's path (not at `sh -c "..."`) and pass the two placeholders as Parameters, as shown above — Dispatcharr substitutes and splits them correctly this way.

**ffmpeg reports "Error opening input: Invalid data found when processing input" / "Error opening input file pipe:0"** — `cvlc` produced no usable data before ffmpeg tried to read it. Check the log for a `cvlc`/shell error just above this line; it usually means the pipeline never actually started (see the syntax-error case above), rather than a live stream problem.

## License

MIT. See [LICENSE](LICENSE).
