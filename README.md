# Profilarr

**Hardware-aware FFmpeg + CVLC stream profiles for Dispatcharr.**

Profilarr provides a simple interface for creating and synchronizing Dispatcharr Stream Profiles and matching Output Profiles for live IPTV streaming.

## Features

* NVIDIA NVENC support
* Intel QSV support
* AMD AMF support
* CPU software encoding
* Passthrough video
* Source FPS, forced 30 FPS, and forced 60 FPS modes
* AAC, AC3, E-AC3, Opus, MP3, and Copy audio options
* Configurable CVLC network caching
* Native Dispatcharr Stream Profile creation
* Native Dispatcharr Output Profile creation
* Automatically synchronizes the selected Stream Profile and Output Profile
* Automatically sets both as the active defaults
* Removes obsolete unlocked Profilarr profiles when configurations change
* Locked Dispatcharr profiles are preserved
* Uses Dispatcharr's native Output Profile pipeline
* No Dispatcharr fork required

## Configuration

Profilarr intentionally uses only three settings.

### 1. Hardware / Video Profile

Choose the video processing method:

| Profile        | FPS          |
| -------------- | ------------ |
| Passthrough    | Source FPS   |
| [NVIDIA] NVENC | Source FPS   |
| [NVIDIA] NVENC | Force 30 FPS |
| [NVIDIA] NVENC | Force 60 FPS |
| [INTEL] QSV    | Source FPS   |
| [INTEL] QSV    | Force 30 FPS |
| [INTEL] QSV    | Force 60 FPS |
| [AMD] AMF      | Source FPS   |
| [AMD] AMF      | Force 30 FPS |
| [AMD] AMF      | Force 60 FPS |
| [CPU] Software | Source FPS   |
| [CPU] Software | Force 30 FPS |
| [CPU] Software | Force 60 FPS |

Passthrough copies the source video without video transcoding.

Hardware profiles use FFmpeg hardware encoders where available.

### 2. Audio Transcoding Override

Available choices:

* AAC
* AC3
* E-AC3
* Opus
* MP3
* Copy

AAC is the default.

When an audio codec is selected, Profilarr creates the corresponding native Dispatcharr Output Profile.

### 3. CVLC Network Cache

Available values:

* 3000 ms
* 6000 ms
* 9000 ms
* 12000 ms
* 15000 ms

The default is **6000 ms**.

## Apply & Synchronize

After selecting the desired settings, press:

**Apply & Synchronize**

Profilarr creates or updates two matching Dispatcharr profiles.

### Stream Profile

Example:

```text
Profilarr Profile - [NVIDIA] NVENC (Source FPS) + Audio: AAC
```

The Stream Profile launches the Profilarr supervisor and passes:

* User agent
* Stream URL
* Video encoder
* Audio selection
* FPS mode
* CVLC network cache

### Output Profile

Example:

```text
Profilarr Output - [NVIDIA] NVENC (Source FPS) + Audio: AAC
```

The Output Profile is a native Dispatcharr FFmpeg pipe stage.

The video is copied through this stage:

```text
-c:v copy
```

The selected audio codec is transcoded by the Output Profile.

This keeps video processing in the Profilarr supervisor while allowing Dispatcharr's native Output Profile system to handle the final output stage.

## Profile Defaults

Profilarr automatically sets the newly synchronized profiles as the defaults.

The Stream Profile default is updated through Dispatcharr's native Stream Settings.

The live Output Profile default is updated through the Dispatcharr user's native `custom_properties["output_profile"]` setting.

There is intentionally **no separate "Set as Default" button**.

Every successful **Apply & Synchronize** operation makes the selected profiles the active defaults.

## Runtime Architecture

Profilarr uses:

```text
Dispatcharr
    |
    v
Profilarr Stream Profile
    |
    v
Profilarr wrapper
    |
    v
Profilarr supervisor
    |
    v
FFmpeg
    |
    v
CVLC
    |
    v
Dispatcharr Output Profile
    |
    v
Live MPEG-TS stream
```

FFmpeg performs the selected video processing.

CVLC provides the network buffering layer.

The native Dispatcharr Output Profile performs the final audio/output stage.

## Installation Directory

Profilarr is completely self-contained under:

```text
/data/plugins/profilarr
```

Runtime files include:

```text
/data/plugins/profilarr/
├── profilarr-supervisor.py
├── profilarr.sh
├── profilarr-nvidia.sh
├── profilarr-amd.sh
├── profilarr-intel.sh
├── profilarr-cpu.sh
└── .installed_version
```

The plugin no longer uses:

```text
/data/profilarr
```

All Profilarr runtime scripts and supervisor files remain under the plugin directory.

## Generated Profile Names

Profilarr uses predictable names.

Stream Profile:

```text
Profilarr Profile - [PROFILE] + Audio: [AUDIO]
```

Output Profile:

```text
Profilarr Output - [PROFILE] + Audio: [AUDIO]
```

For example:

```text
Profilarr Profile - [NVIDIA] NVENC (Force 30 FPS) + Audio: AC3
```

and:

```text
Profilarr Output - [NVIDIA] NVENC (Force 30 FPS) + Audio: AC3
```

Only the currently selected unlocked Profilarr profiles are retained.

Locked profiles are never removed by Profilarr.

## Hardware Requirements

### NVIDIA

Requires an NVIDIA GPU with an FFmpeg NVENC-capable encoder and working NVIDIA drivers.

Profilarr uses:

```text
h264_nvenc
```

for its NVIDIA H.264 profiles.

### Intel

Requires an Intel GPU supported by FFmpeg QSV.

Profilarr uses:

```text
h264_qsv
```

for its Intel H.264 profiles.

### AMD

Requires an AMD GPU supported by FFmpeg AMF.

Profilarr uses:

```text
h264_amf
```

for its AMD H.264 profiles.

### CPU

CPU profiles use FFmpeg software encoding:

```text
libx264
```

CPU Source FPS is supported.

The current CPU profiles do not apply FPS overrides.

## Testing

NVIDIA profiles have been tested with:

* NVENC Source FPS
* NVENC Force 30 FPS
* NVENC Force 60 FPS

Passthrough is also supported.

Intel and AMD hardware profiles should be validated on systems containing the corresponding hardware.

## Troubleshooting

### Stream Profile does not start

Check the generated Stream Profile command:

```text
/data/plugins/profilarr/profilarr-*.sh
```

Verify the scripts are executable.

### Check Profilarr files

```bash
docker exec dispatcharr ls -la /data/plugins/profilarr
```

### Check for old installation paths

```bash
docker exec dispatcharr sh -c 'grep -RIn --exclude="*.pyc" "/data/profilarr" /data/plugins/profilarr 2>/dev/null || echo "No old Profilarr path references found"'
```

### Check generated profiles

```bash
docker exec dispatcharr python3 manage.py shell -c '
from core.models import StreamProfile, OutputProfile

for p in StreamProfile.objects.filter(name__istartswith="Profilarr Profile -"):
    print("STREAM:", p.id, p.name, p.command, p.parameters)

for p in OutputProfile.objects.filter(name__istartswith="Profilarr Output -"):
    print("OUTPUT:", p.id, p.name, p.command, p.parameters)
'
```

## Version

**2.1.4**

## Author

**Tw1zT3d2four7**

## License

See `LICENSE`.

