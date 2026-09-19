<div align="center">
  <img src="logo.png" alt="Profilarr logo" width="140" />

  # Profilarr

  **Hardware-aware FFmpeg + CVLC stream profiles for Dispatcharr**

  <p>
    Build one clean, reusable Stream Profile around your available video encoder family,<br>
    while keeping video codec and audio transcoding choices simple and independent.
  </p>

  <p>
    <img src="https://img.shields.io/badge/version-2.0.4-0f172a?style=for-the-badge" alt="Version 2.0.4" />
    <img src="https://img.shields.io/badge/Dispatcharr-plugin-2563eb?style=for-the-badge" alt="Dispatcharr Plugin" />
    <img src="https://img.shields.io/badge/FFmpeg-supported-007808?style=for-the-badge" alt="FFmpeg" />
    <img src="https://img.shields.io/badge/license-MIT-6b7280?style=for-the-badge" alt="MIT License" />
  </p>

  <p>
    <b>NVIDIA NVENC</b> · <b>AMD AMF</b> · <b>Intel QSV</b> · <b>CPU Software Encoding</b>
  </p>
</div>

---

## Overview

Profilarr is a Dispatcharr plugin that creates and manages a hardware-aware Stream Profile for IPTV/live-stream processing.

The project is designed around a simple idea: **select the hardware family, select the video codec you want, select the audio behavior you want, and let Profilarr resolve the actual FFmpeg encoder and build the Stream Profile for you.**

Profilarr launches a small supervisor process which manages an FFmpeg → CVLC pipeline. FFmpeg handles provider input, reconnect behavior, timestamp cleanup, optional video/audio transcoding, and MPEG-TS output. CVLC provides the downstream buffering/output stage used by the stream profile.

### Supported video families

| Profile | Hardware / encoder family | H.264 | HEVC | AV1 |
|---|---|:---:|:---:|:---:|
| **Profilarr Default** | Source video copy | ✅ Copy | — | — |
| **[NVIDIA] NVENC** | NVIDIA NVENC | `h264_nvenc` | `hevc_nvenc` | `av1_nvenc`* |
| **[AMD] AMF** | AMD AMF | `h264_amf` | `hevc_amf` | `av1_amf`* |
| **[INTEL] QSV** | Intel Quick Sync | `h264_qsv` | `hevc_qsv` | `av1_qsv`* |
| **[CPU] Software** | Software encoders | `libx264` | `libx265` | `libsvtav1` |

\* FFmpeg may contain an encoder even when a particular GPU generation cannot actually encode that format. Profilarr validates FFmpeg encoder availability before creating the profile, but **hardware-generation support still matters**. For example, an older NVIDIA GPU can expose `av1_nvenc` in FFmpeg while not supporting AV1 encoding in hardware.

---

## ✨ What's New in v2.0.4

Version **2.0.4** is a major redesign of Profilarr's profile model.

### Hardware-first profiles

Profiles now represent the **video encoder family**, rather than treating every codec/frame-rate combination as a separate profile.

Available hardware families:

- 🟢 **NVIDIA NVENC**
- 🔴 **AMD AMF**
- 🔵 **Intel QSV**
- ⚪ **CPU Software Encoding**
- ⚫ **Profilarr Default / Copy**

This makes the configuration easier to understand and gives the same UI structure to users with different hardware.

### Video transcoding override

Video codec selection is now independent of the profile name.

Choose:

- **Default / Copy** — do not re-encode video
- **H.264**
- **HEVC**
- **AV1**

Profilarr automatically maps the selected codec to the encoder belonging to the selected hardware family.

Examples:

```text
NVIDIA + H.264  → h264_nvenc
NVIDIA + HEVC   → hevc_nvenc
NVIDIA + AV1    → av1_nvenc

AMD + H.264     → h264_amf
AMD + HEVC      → hevc_amf
AMD + AV1       → av1_amf

Intel + H.264   → h264_qsv
Intel + HEVC    → hevc_qsv
Intel + AV1     → av1_qsv

CPU + H.264     → libx264
CPU + HEVC      → libx265
CPU + AV1       → libsvtav1
```

### Independent audio override

Audio is deliberately separate from video hardware.

Available audio modes:

- **Default / Copy**
- **AAC** — 192 kb/s stereo
- **AC3** — 192 kb/s stereo
- **E-AC3** — 192 kb/s stereo
- **Opus** — 128 kb/s stereo
- **MP3** — 192 kb/s stereo

This means you can, for example, use NVIDIA H.264 hardware encoding while independently selecting AAC audio.

### Stream Profile generation

When **Apply & Synchronize Stream Profile** is pressed, Profilarr:

1. Reads the saved plugin settings.
2. Validates the profile and codec combination.
3. Resolves the real FFmpeg encoder.
4. Checks that the selected FFmpeg encoder exists in the Dispatcharr container.
5. Removes previous unlocked Profilarr-generated profiles with the same prefix.
6. Creates a new active Dispatcharr `StreamProfile`.
7. Optionally sets that profile as Dispatcharr's systemwide default.

The generated profile points to a self-contained wrapper under `/data/profilarr/`.

---

## 🧩 Dispatcharr Plugin Architecture

Profilarr uses Dispatcharr's current plugin manifest format with both `plugin.json` and `plugin.py`.

Dispatcharr supports static `select` fields, so Profilarr intentionally keeps the settings UI simple and performs hardware/encoder validation when the profile is applied. The current Dispatcharr plugin API does not provide a documented dependent/cascading select control for dynamically changing the codec list based on another selection. citeturn0search0

### Plugin settings

| Setting | Options | Purpose |
|---|---|---|
| **Profile Name Prefix** | Custom text | Prefix for the generated Stream Profile |
| **Hardware / Video Profile** | Default, NVIDIA, AMD, Intel, CPU | Selects the video encoder family |
| **Video Transcoding Override** | Copy, H.264, HEVC, AV1 | Selects the desired video codec |
| **Audio Transcoding Override** | Copy, AAC, AC3, E-AC3, Opus, MP3 | Selects audio behavior independently |
| **Set as Systemwide Default Profile** | On / Off | Makes the generated profile Dispatcharr's default |

### Plugin actions

**Apply & Synchronize Stream Profile**

Creates/updates the active Profilarr Stream Profile using the current settings.

**Refresh Scripts & Detection**

Regenerates all wrapper scripts and refreshes FFmpeg/hardware capability detection.

---

## ⚙️ How the Stream Pipeline Works

Profilarr uses the following pipeline:

```text
                  ┌─────────────────────┐
Provider Stream → │       FFmpeg        │
                  │                     │
                  │ • reconnect         │
                  │ • timestamp cleanup │
                  │ • packet handling   │
                  │ • video encode      │
                  │ • audio encode      │
                  │ • MPEG-TS output    │
                  └──────────┬──────────┘
                             │ MPEG-TS
                             ▼
                  ┌─────────────────────┐
                  │        CVLC         │
                  │                     │
                  │ • network buffering │
                  │ • MPEG-TS output    │
                  └──────────┬──────────┘
                             │
                             ▼
                       Dispatcharr
                             │
                             ▼
                     Emby / IPTV Client
```

### FFmpeg input handling

The FFmpeg stage uses reconnect and stream-stability options intended for live IPTV sources, including:

- HTTP reconnect handling
- reconnect-at-EOF
- reconnect for streamed sources
- reconnect delay limiting
- multiple HTTP requests
- non-seekable input handling
- corrupt-packet discard
- regenerated presentation timestamps
- negative timestamp correction
- larger probe/analyze windows for difficult streams

### MPEG-TS output handling

The output stage includes:

- `pat_pmt_at_frames`
- `resend_headers`
- `initial_discontinuity`
- immediate packet flushing
- zero mux delay/preload
- expanded muxing queue

These settings are intended to produce a more predictable MPEG-TS stream for downstream IPTV clients and applications.

---

## 🛡️ Process Supervision & Cleanup

Profilarr does not rely on a shell `trap` alone to clean up FFmpeg and CVLC.

The plugin launches `profilarr-supervisor.py`, which becomes the parent process for the FFmpeg and CVLC pipeline.

The supervisor uses Linux:

```text
PR_SET_PDEATHSIG
```

This tells Linux to deliver `SIGKILL` to the supervisor when its parent process dies. The FFmpeg and CVLC children also receive the same parent-death behavior.

This is important for Dispatcharr because a process can be terminated with `SIGKILL`, where a normal shell `trap` cannot execute cleanup code.

### Process tree

```text
Dispatcharr
    │
    └── profilarr-*.sh
            │
            └── profilarr-supervisor.py
                    ├── ffmpeg
                    └── cvlc
```

When the Dispatcharr-launched process is terminated, Profilarr is designed to prevent orphaned FFmpeg/CVLC processes from being left behind.

---

## 📁 Installed Files

When Profilarr is initialized, it creates the following under `/data/profilarr/`:

```text
/data/profilarr/
├── profilarr-supervisor.py
├── profilarr.sh
├── profilarr-nvidia.sh
├── profilarr-amd.sh
├── profilarr-intel.sh
├── profilarr-cpu.sh
├── .installed_version
└── run/
    └── <pid>.pid
```

### Wrapper scripts

The wrappers are intentionally small. They all launch the same supervisor with a different hardware-family key.

For example:

```sh
#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/profilarr-supervisor.py" "nvidia" "$@"
```

Dispatcharr passes the stream-specific arguments through to the wrapper, including the user agent, source URL, resolved video encoder, and audio override.

---

## 🖥️ Hardware Requirements

Profilarr does not install GPU drivers, CUDA, Intel media drivers, AMD drivers, FFmpeg, or CVLC. Those components must already be available in the Dispatcharr environment.

### NVIDIA

For NVIDIA hardware, the Dispatcharr container must be able to access the GPU and the NVIDIA Video Codec functionality.

A useful verification is:

```bash
docker exec dispatcharr sh -c 'nvidia-smi -L'
```

and:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "h264_nvenc|hevc_nvenc|av1_nvenc"'
```

You can inspect a specific encoder with:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -h encoder=h264_nvenc'
```

### AMD

AMD users need an FFmpeg build with the required AMF encoders and a container environment capable of accessing the appropriate AMD hardware/driver stack.

Check for:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "h264_amf|hevc_amf|av1_amf"'
```

AMF availability is highly dependent on the operating system, FFmpeg build, driver stack, and hardware generation. A profile appearing in Profilarr does not guarantee that every AMD GPU supports every listed codec.

### Intel

Intel users need an FFmpeg build with QSV encoders and an accessible Intel media device/driver stack.

Check for:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "h264_qsv|hevc_qsv|av1_qsv"'
```

### CPU

CPU encoding uses FFmpeg software encoders when available:

- `libx264`
- `libx265`
- `libsvtav1`

CPU encoding does not require a GPU, but transcoding performance depends heavily on processor speed, source resolution, frame rate, codec, and selected encoder settings.

---

## ⚠️ Encoder Availability vs. Hardware Support

One important distinction when troubleshooting hardware encoding:

**FFmpeg listing an encoder does not necessarily mean the installed hardware supports it.**

For example, FFmpeg may list `av1_nvenc` because the encoder is compiled into the FFmpeg binary, while an older NVIDIA GPU cannot actually perform AV1 encoding.

Profilarr therefore uses FFmpeg's encoder list as a first-level validation. Actual hardware support remains dependent on:

- GPU generation
- driver version
- container GPU exposure
- FFmpeg build
- codec support in the hardware
- pixel-format support
- resolution/frame-rate limits

When a hardware codec fails at runtime, the Dispatcharr/FFmpeg logs are the authoritative place to investigate the underlying error.

---

## 🚀 Installation

Profilarr is distributed as a Dispatcharr plugin ZIP.

### Recommended installation

1. Download the latest Profilarr release ZIP from the GitHub repository.
2. Open the **Plugins** page in Dispatcharr.
3. Use **Import** and upload the ZIP.
4. Enable Profilarr.
5. Open the Profilarr settings.
6. Choose the hardware/video profile.
7. Choose the video override.
8. Choose the audio override.
9. Choose whether Profilarr should become the systemwide default Stream Profile.
10. Click **Apply & Synchronize Stream Profile**.

Dispatcharr's current plugin documentation specifies importing a ZIP containing a plugin folder with `plugin.py`; the current plugin standard also supports `plugin.json` for safe metadata discovery. citeturn0search0

### After updating an existing installation

If Dispatcharr appears to retain an older Profilarr version:

1. Remove/disable the old Profilarr installation if necessary.
2. Import the new release ZIP.
3. Refresh the Plugins page.
4. Confirm the displayed version is **2.0.4**.
5. Use **Refresh Scripts & Detection**.
6. Confirm `/data/profilarr/.installed_version` reports `2.0.4`.

---

## 🔧 Configuration Examples

### NVIDIA H.264 + AAC

```text
Hardware / Video Profile:       [NVIDIA] NVENC
Video Transcoding Override:     H.264
Audio Transcoding Override:     AAC
```

Result:

```text
Video encoder: h264_nvenc
Audio encoder: aac
```

### NVIDIA HEVC + Copy Audio

```text
Hardware / Video Profile:       [NVIDIA] NVENC
Video Transcoding Override:     HEVC
Audio Transcoding Override:     Default / Copy
```

Result:

```text
Video encoder: hevc_nvenc
Audio: copy
```

### CPU H.264 + Opus

```text
Hardware / Video Profile:       [CPU] Software
Video Transcoding Override:     H.264
Audio Transcoding Override:     Opus
```

Result:

```text
Video encoder: libx264
Audio encoder: libopus
```

### Default / passthrough video

```text
Hardware / Video Profile:       Profilarr Default
Video Transcoding Override:     Default / Copy
Audio Transcoding Override:     AAC
```

Result:

```text
Video: copy
Audio encoder: aac
```

---

## 🧪 Testing & Compatibility

NVIDIA functionality is the primary development/test environment for the current release. **AMD and Intel support is included in the architecture but needs testing across real-world hardware configurations.**

If you are testing AMD or Intel, useful information to report includes:

- GPU/CPU model
- Dispatcharr version
- FFmpeg version
- Linux distribution and kernel
- selected Profilarr hardware profile
- selected video codec
- selected audio codec
- whether the Stream Profile was created
- whether the channel starts
- buffering/freezing behavior
- audio/video synchronization
- relevant FFmpeg or Dispatcharr log output

Please report failures as well as successful tests. Hardware compatibility issues are often specific to the GPU generation, driver stack, FFmpeg build, or container configuration.

---

## 🛠️ Troubleshooting

### "FFmpeg encoder ... is not available"

Check the encoder from inside the Dispatcharr container:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "h264_nvenc|hevc_nvenc|av1_nvenc|h264_amf|hevc_amf|av1_amf|h264_qsv|hevc_qsv|av1_qsv|libx264|libx265|libsvtav1"'
```

If the encoder is missing, Profilarr cannot use it until the Dispatcharr FFmpeg build provides it.

### NVIDIA encoder is listed but does not start

Check GPU visibility:

```bash
docker exec dispatcharr sh -c 'nvidia-smi -L'
```

Check NVIDIA devices:

```bash
docker exec dispatcharr sh -c 'ls -l /dev/nvidia* 2>/dev/null'
```

Inspect the encoder:

```bash
docker exec dispatcharr sh -c 'ffmpeg -hide_banner -h encoder=h264_nvenc 2>&1 | head -40'
```

A codec appearing in `-encoders` is not by itself proof that the GPU can execute that codec.

### Profile does not appear

Check that Profilarr's action completed successfully and that the generated profile name uses the expected prefix.

You can inspect the plugin files with:

```bash
docker exec dispatcharr sh -c 'ls -lah /data/profilarr/'
```

### Wrapper scripts are missing

Run the Profilarr action:

**Refresh Scripts & Detection**

Then verify:

```bash
docker exec dispatcharr sh -c 'ls -lah /data/profilarr/*.sh /data/profilarr/profilarr-supervisor.py'
```

All five wrappers should exist:

```text
profilarr.sh
profilarr-nvidia.sh
profilarr-amd.sh
profilarr-intel.sh
profilarr-cpu.sh
```

### Playback freezes, loops, or buffers

First verify that the generated Stream Profile is using the expected encoder and audio mode. Then inspect the Dispatcharr FFmpeg logs.

Profilarr's pipeline includes reconnect handling, timestamp regeneration, MPEG-TS header/discontinuity handling, packet flushing, and CVLC network buffering specifically to improve behavior with difficult live IPTV sources. However, no stream-processing pipeline can correct an upstream provider that is consistently delivering broken or unstable media.

---

## 📊 Encoder Mapping Reference

| Hardware profile | H.264 | HEVC | AV1 |
|---|---|---|---|
| NVIDIA | `h264_nvenc` | `hevc_nvenc` | `av1_nvenc` |
| AMD | `h264_amf` | `hevc_amf` | `av1_amf` |
| Intel | `h264_qsv` | `hevc_qsv` | `av1_qsv` |
| CPU | `libx264` | `libx265` | `libsvtav1` |

### Audio mapping

| UI option | FFmpeg encoder | Target bitrate |
|---|---|---:|
| Default / Copy | `copy` | Source |
| AAC | `aac` | 192 kb/s |
| AC3 | `ac3` | 192 kb/s |
| E-AC3 | `eac3` | 192 kb/s |
| Opus | `libopus` | 128 kb/s |
| MP3 | `libmp3lame` | 192 kb/s |

---

## 🔐 Security & Permissions

Profilarr runs as Dispatcharr plugin code inside the Dispatcharr server environment. Like other Dispatcharr plugins, it has access to the application environment and should only be installed from a source you trust. Dispatcharr's documentation explicitly treats plugins as trusted server-side code. citeturn0search0

Profilarr itself does not ask users to enter a Dispatcharr URL, administrator username, or administrator password. It works through Dispatcharr's internal plugin/model interfaces.

---

## 📦 Release Contents

A Profilarr release contains the plugin folder with:

```text
Profilarr/
├── plugin.json
├── plugin.py
├── profilarr-supervisor.py
├── logo.png
├── README.md
└── CHANGELOG.md
```

The plugin generates its runtime wrappers automatically under `/data/profilarr/` when initialized.

---

## 📜 License

Profilarr is released under the **MIT License**.

See [`LICENSE`](LICENSE) for the complete license text when included in the repository.

---

## 🤝 Contributing & Testing

Contributions, bug reports, hardware compatibility reports, and testing feedback are welcome.

If you are opening an issue, include as much of the following as possible:

1. Profilarr version
2. Dispatcharr version
3. FFmpeg version
4. GPU/CPU model
5. Operating system
6. Selected hardware profile
7. Selected video override
8. Selected audio override
9. Exact error message
10. Relevant Dispatcharr/FFmpeg log output

Hardware-specific reports are especially valuable for AMD and Intel testing.

---

## 🔗 Project Links

- **Profilarr:** https://github.com/Tw1zT3d2four7/Profilarr
- **Dispatcharr:** https://github.com/Dispatcharr/Dispatcharr
- **Dispatcharr Plugin Documentation:** https://github.com/Dispatcharr/Dispatcharr/blob/main/Plugins.md

---

<div align="center">

### Profilarr

**Hardware-aware stream processing for Dispatcharr.**

Made by **Tw1zT3d2four7**

</div>
