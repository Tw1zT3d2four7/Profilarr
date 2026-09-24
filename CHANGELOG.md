# Changelog

All notable changes to Profilarr are documented here.

## [2.1.6] - 2026-09-23

### Changed

* Simplified the Profilarr interface to three configuration selectors:

  * Hardware / Video Profile
  * Audio Transcoding Override
  * CVLC Network Cache
* Added explicit hardware and frame-rate selections:

  * Passthrough
  * NVIDIA NVENC Source FPS
  * NVIDIA NVENC Force 30 FPS
  * NVIDIA NVENC Force 60 FPS
  * Intel QSV Source FPS
  * Intel QSV Force 30 FPS
  * Intel QSV Force 60 FPS
  * AMD AMF Source FPS
  * AMD AMF Force 30 FPS
  * AMD AMF Force 60 FPS
  * CPU Software Source FPS
  * CPU Software Force 30 FPS
  * CPU Software Force 60 FPS
* Standardized the audio selection names:

  * AAC
  * AC3
  * E-AC3
  * Opus
  * MP3
  * Copy
* Changed the internal Copy audio label to simply `Copy`.
* Moved the complete Profilarr runtime installation to:

  * `/data/plugins/profilarr`
* Removed use of the previous runtime directory:

  * `/data/profilarr`

### Added

* Native Dispatcharr Output Profile synchronization.
* Matching Stream Profile and Output Profile generation.
* Automatic Stream Profile default synchronization.
* Automatic live Output Profile default synchronization.
* Native FFmpeg Output Profile pipeline using video copy:

  * `-c:v copy`
* Automatic cleanup of obsolete unlocked Profilarr Stream Profiles.
* Automatic cleanup of obsolete unlocked Profilarr Output Profiles.
* Locked Dispatcharr profiles are preserved.
* Predictable matching profile names.

### Profile Naming

Stream Profiles now use:

```text
Profilarr Profile - [PROFILE] + Audio: [AUDIO]
```

Output Profiles use:

```text
Profilarr Output - [PROFILE] + Audio: [AUDIO]
```

### Defaults

* Removed the separate `Set as Default` configuration option.
* `Apply & Synchronize` now automatically makes the generated Stream Profile the Dispatcharr Stream Profile default.
* `Apply & Synchronize` now automatically makes the generated Output Profile the live Output Profile default.

### Runtime

* Profilarr supervisor architecture retained.
* Wrapper scripts remain generated automatically.
* Runtime scripts are installed under `/data/plugins/profilarr`.
* Supervisor and wrapper permissions are enforced during installation.

### Testing

Validated NVIDIA configurations:

* NVIDIA NVENC Source FPS
* NVIDIA NVENC Force 30 FPS
* NVIDIA NVENC Force 60 FPS
* Multiple audio overrides
* CVLC network caching configuration
* Native Stream Profile synchronization
* Native Output Profile synchronization
* Automatic default synchronization

Intel and AMD profiles remain available for hardware-specific validation on systems containing the corresponding GPUs.

---

## [2.0.7]

### Changed

* Continued the Profilarr supervisor architecture.
* Improved hardware-aware stream profile generation.
* Added configurable video, audio, FPS, and network cache controls.
* Improved runtime process management.
* Added supervisor lifecycle handling.

---

## [2.0.6]

### Changed

* Improved profile generation and runtime handling.
* Updated supervisor behavior.
* Improved stream process cleanup and lifecycle management.

---

## [2.0.5]

### Added

* Hardware-aware FFmpeg profiles.
* NVIDIA, AMD, Intel, and CPU encoding support.
* Configurable CVLC network caching.
* Profile generation through the Dispatcharr plugin system.

---

## [2.0.2]

### Changed

* Improved stream supervisor handling.
* Updated generated wrapper scripts.
* Improved FFmpeg/CVLC pipeline stability.

---

## [2.0.1]

### Added

* Initial Profilarr plugin architecture.
* Dispatcharr Stream Profile integration.
* FFmpeg and CVLC streaming pipeline.
* Hardware encoder support.

