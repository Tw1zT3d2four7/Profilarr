# Changelog

## 2.0.7
- NVIDIA, AMD, Intel, and CPU profiles can no longer be applied with a Copy video or Copy audio override — those profiles now require an actual codec for both. Copy remains available only on the Profilarr Default profile.
- Note: the Dispatcharr plugin field schema doesn't support conditionally hiding dropdown options based on another field's selection, so `Copy` still appears in the Video/Audio Transcoding Override lists regardless of the chosen hardware profile. The restriction is enforced at Apply time with a clear rejection message (both in the plugin's own validation and, as a backstop, inside the supervisor itself), and the field descriptions now state the rule up front.

## 2.0.6
- Added CVLC Network Cache selection (3000 / 6000 / 9000 / 12000 / 15000 ms), same selector pattern as the other overrides, replacing the previously hardcoded 6000 ms `--network-caching` value.
- Stream Profile parameters now carry a 6th value (the cache override); wrapper scripts pass it straight through, and the supervisor CLI went from 6 to 7 arguments.

## 2.0.5
- Added Frame Rate Override selection (Default / Force 30 FPS / Force 60 FPS), independent of the Audio Transcoding Override, matching the existing selector pattern.
- Frame Rate Override applies only to NVIDIA, AMD, and Intel hardware profiles, and only when a Video Transcoding Override other than Copy is also selected; both the UI-side validation and the supervisor reject any other combination.
- Forcing FPS sets `-vf fps=...`, `-fps_mode cfr`, and a matching `-g`/`-keyint_min` (2x target fps) on top of the existing hardware encoder settings.
- Stream Profile parameters now carry a 5th value (the FPS override); wrapper scripts and the supervisor CLI were updated accordingly.

## 2.0.2
- Fixed profile creation incorrectly rejecting hardware encoders when the encoder is present in the Dispatcharr container.
- FFmpeg encoder availability is now determined directly from the container FFmpeg encoder list.
- Removed the separate DRM/vendor-family gate that could falsely reject working NVENC/AMF/QSV encoders.
- NVIDIA/AMD/Intel profile selections remain visible; genuinely unavailable codecs are still rejected.


## v2.0.1

- Major architecture redesign around hardware encoder families.
- Added Profilarr Default, NVIDIA NVENC, AMD AMF, Intel QSV, and CPU Software selections.
- Added independent Video Transcoding Override.
- Added independent Audio Transcoding Override.
- Added current Dispatcharr `plugin.json` manifest.
- All five wrapper `.sh` files are generated automatically during installation/update.
- Added runtime FFmpeg encoder and Linux GPU detection/validation.
- Added validation so unavailable hardware/encoders cannot be applied even though all supported choices remain visible in the UI.
- Retained PDEATHSIG supervisor process ownership.
- Retained FFmpeg reconnect/timestamp/MPEG-TS stability handling and 6000 ms CVLC buffering.
