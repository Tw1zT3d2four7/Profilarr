# Profilarr plugin
from __future__ import annotations
import contextlib, os, re, shutil, signal, stat, subprocess
from pathlib import Path
from apps.plugins.models import PluginConfig
from core.models import StreamProfile, OutputProfile, CoreSettings
from apps.accounts.models import User

SUPERVISOR = "profilarr-supervisor.py"

PROFILES = {
    "default": {
        "filename": "profilarr.sh",
        "label": "Profilarr Default",
        "family": "default",
        "encoders": {"copy"},
    },
    "nvidia": {
        "filename": "profilarr-nvidia.sh",
        "label": "[NVIDIA] NVENC",
        "family": "nvidia",
        "encoders": {"h264_nvenc", "hevc_nvenc", "av1_nvenc"},
    },
    "amd": {
        "filename": "profilarr-amd.sh",
        "label": "[AMD] AMF",
        "family": "amd",
        "encoders": {"h264_amf", "hevc_amf", "av1_amf"},
    },
    "intel": {
        "filename": "profilarr-intel.sh",
        "label": "[INTEL] QSV",
        "family": "intel",
        "encoders": {"h264_qsv", "hevc_qsv", "av1_qsv"},
    },
    "cpu": {
        "filename": "profilarr-cpu.sh",
        "label": "[CPU] Software",
        "family": "cpu",
        "encoders": {"libx264", "libx265", "libsvtav1"},
    },
}

AUDIO_OPTIONS = {
    "copy": "Copy",
    "aac": "AAC",
    "ac3": "AC3",
    "eac3": "E-AC3",
    "opus": "Opus",
    "mp3": "MP3",
}

CACHE_OPTIONS = {
    "3000": "3000 ms",
    "6000": "6000 ms (Default)",
    "9000": "9000 ms",
    "12000": "12000 ms",
    "15000": "15000 ms",
}


class Plugin:
    name = "Profilarr"
    version = "2.1.5"
    description = "Hardware-aware FFmpeg + CVLC stream profiles for Dispatcharr."
    author = "Tw1zT3d2four7"
    help_url = "https://github.com/Tw1zT3d2four7/Profilarr"
    dst_dir = "/data/plugins/profilarr"
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
        self.fields = self._fields()
        self.actions = self._actions()

    def _fields(self):
        return [
            {
                "id": "video_profile",
                "label": "Hardware / Video Profile",
                "type": "select",
                "default": "passthrough",
                "options": [
                    {
                        "value": "passthrough",
                        "label": "Passthrough (base video copy)",
                    },
                    {
                        "value": "nvidia_source",
                        "label": "[NVIDIA] NVENC (Source FPS)",
                    },
                    {
                        "value": "nvidia_30",
                        "label": "[NVIDIA] NVENC (Force 30 FPS)",
                    },
                    {
                        "value": "nvidia_60",
                        "label": "[NVIDIA] NVENC (Force 60 FPS)",
                    },
                    {
                        "value": "intel_source",
                        "label": "[INTEL] QSV (Source FPS)",
                    },
                    {
                        "value": "intel_30",
                        "label": "[INTEL] QSV (Force 30 FPS)",
                    },
                    {
                        "value": "intel_60",
                        "label": "[INTEL] QSV (Force 60 FPS)",
                    },
                    {
                        "value": "amd_source",
                        "label": "[AMD] AMF (Source FPS)",
                    },
                    {
                        "value": "amd_30",
                        "label": "[AMD] AMF (Force 30 FPS)",
                    },
                    {
                        "value": "amd_60",
                        "label": "[AMD] AMF (Force 60 FPS)",
                    },
                    {
                        "value": "cpu_source",
                        "label": "[CPU] Software (Source FPS)",
                    },
                    {
                        "value": "cpu_30",
                        "label": "[CPU] Software (Force 30 FPS)",
                    },
                    {
                        "value": "cpu_60",
                        "label": "[CPU] Software (Force 60 FPS)",
                    },
                ],
            },
            {
                "id": "audio_override",
                "label": "Audio Transcoding Override",
                "type": "select",
                "default": "aac",
                "options": [
                    {"value": "aac", "label": "AAC"},
                    {"value": "ac3", "label": "AC3"},
                    {"value": "eac3", "label": "E-AC3"},
                    {"value": "opus", "label": "Opus"},
                    {"value": "mp3", "label": "MP3"},
                    {"value": "copy", "label": "Copy"},
                ],
            },
            {
                "id": "network_caching",
                "label": "CVLC Network Cache (ms)",
                "type": "select",
                "default": "6000",
                "options": [
                    {"value": "3000", "label": "3000"},
                    {"value": "6000", "label": "6000 (Default)"},
                    {"value": "9000", "label": "9000"},
                    {"value": "12000", "label": "12000"},
                    {"value": "15000", "label": "15000"},
                ],
            },
        ]

    def _actions(self):
        return [
            {
                "id": "generate_profile",
                "label": "Apply & Synchronize",
                "button_label": "Apply & Synchronize",
                "button_color": "green",
                "description": (
                    "Create or update the selected Profilarr Stream Profile "
                    "and matching Output Profile."
                ),
            }
        ]

    def _all_files(self):
        return [SUPERVISOR] + [p["filename"] for p in PROFILES.values()]

    def _install(self):
        os.makedirs(self.dst_dir, exist_ok=True)

        src = self.plugin_dir / SUPERVISOR
        dst = Path(self.dst_dir) / SUPERVISOR

        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)

        os.chmod(dst, 0o700)

        for key, p in PROFILES.items():
            wrapper = Path(self.dst_dir) / p["filename"]
            wrapper.write_text(
                f'#!/bin/sh\n'
                f'SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
                f'exec python3 "$SCRIPT_DIR/{SUPERVISOR}" "{key}" "$@"\n'
            )
            os.chmod(wrapper, 0o700)

        (Path(self.dst_dir) / ".installed_version").write_text(
            self.version + "\n"
        )

    def _selection(self):
        return {
            "passthrough": (
                "default",
                "copy",
                "copy",
                "Passthrough (base video copy)",
            ),

            "nvidia_source": (
                "nvidia",
                "h264_nvenc",
                "copy",
                "[NVIDIA] NVENC (Source FPS)",
            ),
            "nvidia_30": (
                "nvidia",
                "h264_nvenc",
                "30",
                "[NVIDIA] NVENC (Force 30 FPS)",
            ),
            "nvidia_60": (
                "nvidia",
                "h264_nvenc",
                "60",
                "[NVIDIA] NVENC (Force 60 FPS)",
            ),

            "intel_source": (
                "intel",
                "h264_qsv",
                "copy",
                "[INTEL] QSV (Source FPS)",
            ),
            "intel_30": (
                "intel",
                "h264_qsv",
                "30",
                "[INTEL] QSV (Force 30 FPS)",
            ),
            "intel_60": (
                "intel",
                "h264_qsv",
                "60",
                "[INTEL] QSV (Force 60 FPS)",
            ),

            "amd_source": (
                "amd",
                "h264_amf",
                "copy",
                "[AMD] AMF (Source FPS)",
            ),
            "amd_30": (
                "amd",
                "h264_amf",
                "30",
                "[AMD] AMF (Force 30 FPS)",
            ),
            "amd_60": (
                "amd",
                "h264_amf",
                "60",
                "[AMD] AMF (Force 60 FPS)",
            ),

            "cpu_source": (
                "cpu",
                "libx264",
                "copy",
                "[CPU] Software (Source FPS)",
            ),
            "cpu_30": (
                "cpu",
                "libx264",
                "30",
                "[CPU] Software (Force 30 FPS)",
            ),
            "cpu_60": (
                "cpu",
                "libx264",
                "60",
                "[CPU] Software (Force 60 FPS)",
            ),
        }

    def _output_parameters(self, audio):
        audio_args = {
            "copy": "-c:a copy",
            "aac": "-c:a aac -b:a 192k -ac 2",
            "ac3": "-c:a ac3 -b:a 192k -ac 2",
            "eac3": "-c:a eac3 -b:a 192k -ac 2",
            "opus": "-c:a libopus -b:a 128k -ac 2",
            "mp3": "-c:a libmp3lame -b:a 192k -ac 2",
        }

        if audio not in audio_args:
            raise ValueError("unknown audio override: " + audio)

        return (
            "-fflags +discardcorrupt+genpts+nobuffer "
            "-probesize 512K "
            "-analyzeduration 0 "
            "-i pipe:0 "
            "-map 0 "
            "-c:v copy "
            f"{audio_args[audio]} "
            "-max_muxing_queue_size 4096 "
            "-flush_packets 1 "
            "-mpegts_flags +pat_pmt_at_frames+resend_headers+initial_discontinuity "
            "-f mpegts "
            "pipe:1"
        )

    def _generate_profile(self):
        video_key = self.settings.get(
            "video_profile",
            "passthrough",
        )
        audio = self.settings.get(
            "audio_override",
            "aac",
        )
        cache = self.settings.get(
            "network_caching",
            "6000",
        )
        selections = self._selection()

        if video_key not in selections:
            return {
                "status": "error",
                "message": "Unknown video profile selection.",
            }

        if audio not in AUDIO_OPTIONS:
            return {
                "status": "error",
                "message": "Unknown audio override.",
            }

        if cache not in CACHE_OPTIONS:
            return {
                "status": "error",
                "message": "Unknown network cache value.",
            }

        profile, video, fps, video_label = selections[video_key]

        audio_label = (
            "AAC"
            if audio == "aac"
            else (
                "Copy"
                if audio == "copy"
                else AUDIO_OPTIONS[audio]
            )
        )

        stream_target = (
            f"Profilarr Profile - {video_label} + Audio: {audio_label}"
        )

        output_target = (
            f"Profilarr Output - {video_label} + Audio: {audio_label}"
        )

        p = PROFILES[profile]

        stream_parameters = (
            f"'{{userAgent}}' '{{streamUrl}}' "
            f"'{video}' '{audio}' '{fps}' '{cache}'"
        )

        output_parameters = self._output_parameters(audio)

        # ---------------------------------------------------------------------
        # STREAM PROFILE CLEANUP
        # ---------------------------------------------------------------------
        for old in StreamProfile.objects.filter(
            name__istartswith="Profilarr Profile -"
        ):
            if not old.locked and old.name != stream_target:
                old.delete()

        # ---------------------------------------------------------------------
        # OUTPUT PROFILE CLEANUP
        # ---------------------------------------------------------------------
        for old in OutputProfile.objects.filter(
            name__istartswith="Profilarr Output -"
        ):
            if not old.locked and old.name != output_target:
                old.delete()

        # ---------------------------------------------------------------------
        # STREAM PROFILE CREATE / UPDATE
        # ---------------------------------------------------------------------
        try:
            existing_stream = StreamProfile.objects.filter(
                name=stream_target,
                locked=False,
            ).first()

            if existing_stream:
                stream_profile = existing_stream
                stream_profile.command = str(
                    Path(self.dst_dir) / p["filename"]
                )
                stream_profile.parameters = stream_parameters
                stream_profile.is_active = True
                stream_profile.save()
            else:
                stream_profile = StreamProfile(
                    name=stream_target,
                    command=str(
                        Path(self.dst_dir) / p["filename"]
                    ),
                    parameters=stream_parameters,
                    is_active=True,
                    locked=False,
                )
                stream_profile.save()

        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Could not create Stream Profile: "
                    f"{type(e).__name__}: {e}"
                ),
            }

        # ---------------------------------------------------------------------
        # OUTPUT PROFILE CREATE / UPDATE
        # ---------------------------------------------------------------------
        try:
            existing_output = OutputProfile.objects.filter(
                name=output_target,
                locked=False,
            ).first()

            if existing_output:
                output_profile = existing_output
                output_profile.command = "ffmpeg"
                output_profile.parameters = output_parameters
                output_profile.is_active = True
                output_profile.save()
            else:
                output_profile = OutputProfile(
                    name=output_target,
                    command="ffmpeg",
                    parameters=output_parameters,
                    is_active=True,
                    locked=False,
                )
                output_profile.save()

        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Could not create Output Profile: "
                    f"{type(e).__name__}: {e}"
                ),
            }

        # ---------------------------------------------------------------------
        # NATIVE DISPATCHARR STREAM PROFILE DEFAULT
        # ---------------------------------------------------------------------
        try:
            CoreSettings._update_group(
                "stream_settings",
                "Stream Settings",
                {
                    "default_stream_profile": stream_profile.id
                },
            )
        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Profiles synchronized, but Stream Profile default "
                    f"could not be changed: "
                    f"{type(e).__name__}: {e}"
                ),
            }

        # ---------------------------------------------------------------------
        # NATIVE DISPATCHARR LIVE OUTPUT PROFILE DEFAULT
        # ---------------------------------------------------------------------
        try:
            user = User.objects.get(id=1)

            custom_properties = dict(user.custom_properties or {})
            custom_properties["output_profile"] = output_profile.id

            user.custom_properties = custom_properties
            user.save(update_fields=["custom_properties"])

        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Profiles synchronized and Stream Profile default "
                    f"changed, but Output Profile default could not be "
                    f"changed: {type(e).__name__}: {e}"
                ),
            }

        return {
            "status": "ok",
            "message": (
                f"Profilarr synchronized: {stream_target} | "
                f"{output_target} | "
                f"Stream Default: {stream_profile.id} | "
                f"Output Default: {output_profile.id} | "
                f"Cache: {cache} ms"
            ),
        }

    def stop(self, context):
        run_dir = Path(self.dst_dir) / "run"

        for pid_file in run_dir.glob("*.pid"):
            with contextlib.suppress(Exception):
                os.kill(
                    int(pid_file.read_text().strip()),
                    signal.SIGTERM,
                )

            with contextlib.suppress(OSError):
                pid_file.unlink()

    def run(self, action, params, context):
        self.settings = context.get("settings", {}) or {}

        if action == "generate_profile":
            return self._generate_profile()

        return {
            "status": "error",
            "message": f"Unknown action: {action}",
        }
