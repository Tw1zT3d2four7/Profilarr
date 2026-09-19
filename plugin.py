# Profilarr 2.0.4
from __future__ import annotations

import contextlib
import os
import re
import shutil
import signal
import stat
import subprocess
from pathlib import Path

from apps.plugins.models import PluginConfig
from core.models import StreamProfile

SUPERVISOR = "profilarr-supervisor.py"

PROFILES = {
    "default": {"filename": "profilarr.sh", "label": "Profilarr Default", "family": "default", "encoders": {"copy"}},
    "nvidia": {"filename": "profilarr-nvidia.sh", "label": "[NVIDIA] NVENC", "family": "nvidia", "encoders": {"copy", "h264_nvenc", "hevc_nvenc", "av1_nvenc"}},
    "amd": {"filename": "profilarr-amd.sh", "label": "[AMD] AMF", "family": "amd", "encoders": {"copy", "h264_amf", "hevc_amf", "av1_amf"}},
    "intel": {"filename": "profilarr-intel.sh", "label": "[INTEL] QSV", "family": "intel", "encoders": {"copy", "h264_qsv", "hevc_qsv", "av1_qsv"}},
    "cpu": {"filename": "profilarr-cpu.sh", "label": "[CPU] Software", "family": "cpu", "encoders": {"copy", "libx264", "libx265", "libsvtav1"}},
}

VIDEO_OPTIONS = {
    "copy": ("Default / Copy", "Copy source video without re-encoding."),
    "h264": ("H.264", "H.264 video encoding using the selected hardware family."),
    "hevc": ("HEVC", "HEVC video encoding using the selected hardware family."),
    "av1": ("AV1", "AV1 video encoding using the selected hardware family."),
}

VIDEO_ENCODERS = {
    "default": {"copy": "copy"},
    "nvidia": {"copy": "copy", "h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"},
    "amd": {"copy": "copy", "h264": "h264_amf", "hevc": "hevc_amf", "av1": "av1_amf"},
    "intel": {"copy": "copy", "h264": "h264_qsv", "hevc": "hevc_qsv", "av1": "av1_qsv"},
    "cpu": {"copy": "copy", "h264": "libx264", "hevc": "libx265", "av1": "libsvtav1"},
}


AUDIO_OPTIONS = {
    "copy": "Default / Copy", "aac": "AAC", "ac3": "AC3", "eac3": "E-AC3", "opus": "Opus", "mp3": "MP3"
}
AUDIO_ENCODERS = {"aac": "aac", "ac3": "ac3", "eac3": "eac3", "opus": "libopus", "mp3": "libmp3lame"}


def _run(cmd, timeout=8):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _ffmpeg_encoders():
    r = _run(["ffmpeg", "-hide_banner", "-encoders"], 10)
    if not r or r.returncode != 0:
        return set()
    result = set()
    for line in r.stdout.splitlines():
        m = re.match(r"^\s*[A-Z.]{6}\s+(\S+)", line)
        if m:
            result.add(m.group(1))
    return result


def _gpu_vendors():
    vendors = set()
    for card in Path("/sys/class/drm").glob("card[0-9]*"):
        try:
            v = (card / "device/vendor").read_text().strip().lower()
        except OSError:
            continue
        vendors.update({"nvidia"} if v == "0x10de" else {"amd"} if v == "0x1002" else {"intel"} if v == "0x8086" else set())
    if "nvidia" not in vendors:
        r = _run(["nvidia-smi", "-L"], 5)
        if r and r.returncode == 0:
            vendors.add("nvidia")
    return vendors


def detect_capabilities():
    enc = _ffmpeg_encoders()
    vendors = _gpu_vendors()
    available = {"default", "cpu"}
    if "nvidia" in vendors and enc & {"h264_nvenc", "hevc_nvenc", "av1_nvenc"}:
        available.add("nvidia")
    if "amd" in vendors and enc & {"h264_amf", "hevc_amf", "av1_amf"}:
        available.add("amd")
    if "intel" in vendors and enc & {"h264_qsv", "hevc_qsv", "av1_qsv"}:
        available.add("intel")
    return {"encoders": enc, "vendors": vendors, "families": available}


class Plugin:
    name = "Profilarr"
    version = "2.0.4"
    description = "Hardware-family video profiles with independent video and audio transcoding overrides."
    author = "Tw1zT3d2four7"
    help_url = "https://github.com/Tw1zT3d2four7/Profilarr"
    dst_dir = "/data/profilarr"
    plugin_dir = Path(__file__).resolve().parent
    plugin_key = plugin_dir.name.replace(" ", "_").lower()

    def __init__(self):
        try:
            self.context = PluginConfig.objects.get(key=self.plugin_key)
            self.settings = self.context.settings or {}
        except PluginConfig.DoesNotExist:
            self.context = None
            self.settings = {}
        self._install()
        self.capabilities = detect_capabilities()
        self.fields = self._fields()
        self.actions = self._actions()

    def _fields(self):
        return [
            {"id": "profile_name", "label": "Profile Name Prefix *", "type": "string", "default": "Profilarr", "description": "Base name used for the generated Dispatcharr Stream Profile."},
            {"id": "selected_profile", "label": "Hardware / Video Profile", "type": "select", "default": "default", "options": [{"value": k, "label": v["label"]} for k, v in PROFILES.items()], "description": "All five profiles are available. Profilarr validates hardware/FFmpeg support when applied."},
            {"id": "video_override", "label": "Video Transcoding Override", "type": "select", "default": "copy", "options": [{"value": k, "label": v[0]} for k, v in VIDEO_OPTIONS.items()], "description": "Select the video codec. Profilarr automatically uses the encoder belonging to the selected hardware/video profile."},
            {"id": "audio_override", "label": "Audio Transcoding Override", "type": "select", "default": "copy", "options": [{"value": k, "label": v} for k, v in AUDIO_OPTIONS.items()], "description": "Independent of video hardware."},
            {"id": "set_as_default", "label": "Set as Systemwide Default Profile", "type": "boolean", "default": True, "description": "Automatically sets the generated profile as the Dispatcharr default."},
        ]

    def _actions(self):
        return [
            {"id": "generate_profile", "label": "Generate and Overwrite Profile", "button_label": "Apply & Synchronize Stream Profile", "button_color": "green", "description": "Validate selections and create the active Stream Profile."},
            {"id": "reinstall", "label": "Refresh Profilarr", "button_label": "Refresh Scripts & Detection", "button_color": "blue", "description": "Regenerate all five wrapper scripts and refresh FFmpeg/hardware detection."},
        ]

    def _all_files(self):
        return [SUPERVISOR] + [p["filename"] for p in PROFILES.values()]

    def _install(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        src = self.plugin_dir / SUPERVISOR
        dst = Path(self.dst_dir) / SUPERVISOR
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)
        for key, p in PROFILES.items():
            wrapper = Path(self.dst_dir) / p["filename"]
            wrapper.write_text(f'#!/bin/sh\nSCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec python3 "$SCRIPT_DIR/{SUPERVISOR}" "{key}" "$@"\n')
            os.chmod(wrapper, 0o755)
        (Path(self.dst_dir) / ".installed_version").write_text(self.version + "\n")

    @staticmethod
    def _valid_name(name):
        return bool(name) and bool(re.match(r"^[\w .\-]{1,64}$", name))

    def _validate(self, profile, video, audio):
        caps = detect_capabilities()
        if profile not in VIDEO_ENCODERS:
            return "Unknown hardware profile."
        if video not in VIDEO_ENCODERS[profile]:
            return f"Video override {video} is not available for the selected {PROFILES[profile]['label']} profile."
        encoder = VIDEO_ENCODERS[profile][video]
        if encoder != "copy" and encoder not in caps["encoders"]:
            return f"FFmpeg encoder {encoder} is not available in this Dispatcharr container."
        if audio not in AUDIO_OPTIONS:
            return "Unknown audio override."
        if audio != "copy" and AUDIO_ENCODERS.get(audio) not in caps["encoders"]:
            return f"FFmpeg audio encoder {AUDIO_ENCODERS.get(audio)} is not available."
        return None

    def _generate_profile(self):
        base = (self.settings.get("profile_name") or "Profilarr").strip()
        profile = self.settings.get("selected_profile", "default")
        video = self.settings.get("video_override", "copy")
        audio = self.settings.get("audio_override", "copy")
        if not self._valid_name(base):
            return {"status": "error", "message": "Invalid profile prefix."}
        error = self._validate(profile, video, audio)
        if error:
            return {"status": "error", "message": error}
        p = PROFILES[profile]
        resolved_video = VIDEO_ENCODERS[profile][video]
        target = f"{base} Profile ({p['filename']})"
        for old in StreamProfile.objects.filter(name__istartswith=f"{base} Profile ("):
            if not old.locked:
                old.delete()
        new = StreamProfile(name=target, command=str(Path(self.dst_dir) / p["filename"]), parameters=f"'{{userAgent}}' '{{streamUrl}}' '{resolved_video}' '{audio}'", is_active=True, locked=False)
        try:
            new.save()
        except Exception as e:
            return {"status": "error", "message": f"Could not create profile: {type(e).__name__}: {e}"}
        msg = f"Profilarr 2.0.4 synchronized: {p['label']} | Video: {VIDEO_OPTIONS[video][0]} ({resolved_video}) | Audio: {AUDIO_OPTIONS[audio]}"
        if self.settings.get("set_as_default", True):
            try:
                from core.models import CoreSettings
                CoreSettings._update_group("stream_settings", "Stream Settings", {"default_stream_profile": new.id})
            except Exception as e:
                msg += f" (global default not changed: {type(e).__name__}: {e})"
        return {"status": "ok", "message": msg}

    def _reinstall(self):
        try:
            self._install()
            caps = detect_capabilities()
            return {"status": "ok", "message": f"Profilarr 2.0.4 refreshed. Generated all five wrappers. FFmpeg encoders detected: {len(caps['encoders'])}; GPU families detected: {', '.join(sorted(caps['vendors'])) or 'none'}"}
        except OSError as e:
            return {"status": "error", "message": str(e)}

    def stop(self, context):
        run_dir = Path(self.dst_dir) / "run"
        for pid_file in run_dir.glob("*.pid"):
            with contextlib.suppress(Exception):
                os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
            with contextlib.suppress(OSError):
                pid_file.unlink()

    def run(self, action, params, context):
        self.settings = context.get("settings", {}) or {}
        if action == "generate_profile":
            return self._generate_profile()
        if action == "reinstall":
            return self._reinstall()
        return {"status": "error", "message": f"Unknown action: {action}"}
