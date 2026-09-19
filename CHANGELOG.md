# Changelog

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
