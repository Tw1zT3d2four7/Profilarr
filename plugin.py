"""Profilarr Dispatcharr plugin.

Installs the selectable stream scripts plus the bundled supervisor into
/data/profilarr/. The scripts exec the supervisor, which owns ffmpeg and cvlc.
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import signal
import stat
from pathlib import Path

from apps.plugins.models import PluginConfig
from core.models import StreamProfile

# Catalog map structuring filenames, clean labels, descriptions, and tab layout categories
PROFILES = {
    "passthrough": ("profilarr.sh", "Passthrough (base)", "Video passthrough (-c:v copy, no re-encode) | cvlc.", "Default Profile"),
    "uncapped": ("profilarr-uncapped.sh", "Uncapped FPS (Nvidia)", "NVENC re-encode at 8Mbps CBR with source frame rate preserved | cvlc.", "Nvidia Encoding Options"),
    "fps30": ("profilarr-30fps-capped.sh", "30 FPS Capped (Nvidia)", "NVENC re-encode forced to 29.97fps | cvlc.", "Nvidia Encoding Options"),
    "fps60": ("profilarr-60fps-forced.sh", "60 FPS Forced (Nvidia)", "NVENC re-encode forced to 59.94fps | cvlc.", "Nvidia Encoding Options"),
    "cpu_uncapped": ("profilarr-cpu-uncapped.sh", "Uncapped FPS (CPU libx264)", "Software x264 re-encode at 8Mbps CBR with source frame rate preserved | cvlc.", "CPU Encoding Options"),
    "cpu_fps30": ("profilarr-cpu-30fps.sh", "30 FPS Capped (CPU libx264)", "Software x264 re-encode forced to 29.97fps | cvlc.", "CPU Encoding Options"),
    "cpu_fps60": ("profilarr-cpu-60fps.sh", "60 FPS Forced (CPU libx264)", "Software x264 re-encode forced to 59.94fps | cvlc.", "CPU Encoding Options"),
}
SUPERVISOR = "profilarr-supervisor.py"

class Plugin:
    name = "Profilarr"
    version = "1.0.8"
    description = "Hybrid ffmpeg + cvlc stream profile with auto-overwriting selectable variants."
    author = "Tw1zT3d2four7"
    help_url = "https://github.com"
    dst_dir = "/data/profilarr"
    plugin_dir = Path(__file__).resolve().parent
    plugin_key = plugin_dir.name.replace(" ", "_").lower()

    @staticmethod
    def _parse_version(s):
        if not s: return None
        try: return tuple(int(x) for x in s.strip().lstrip("v").split("."))
        except (ValueError, AttributeError): return None

    def __init__(self):
        try:
            self.context = PluginConfig.objects.get(key=self.plugin_key)
            self.settings = self.context.settings or {}
        except PluginConfig.DoesNotExist:
            self.context = None
            self.settings = {}

        if not all(os.path.isfile(self._dst_file(f)) for f in self._all_files()):
            self._install()
        else:
            local = self._read_installed_version()
            packaged = self._parse_version(self.version)
            if packaged is not None and (local is None or packaged > local):
                self._install()

        # Visual form setup with distinct field attributes
        self.fields = [
            {
                "id": "profile_name", "label": "Profile Name Prefix *", "type": "string",
                "default": "Profilarr",
                "description": "Base name used for your active Dispatcharr Stream Profile configuration."
            },
            {
                "id": "selected_profile", "label": "Select Active Stream Profile Variant",
                "type": "select", "default": "passthrough",
                "description": "Choose the active pipeline configuration. Generating a profile automatically replaces the previous variant.",
                "options": [
                    {"value": k, "label": f"[{v[3]}] {v[1]}", "description": v[2]} for k, v in PROFILES.items()
                ]
            },
            {
                "id": "set_as_default", "label": "Set as Systemwide Default Profile",
                "type": "boolean", "default": True,
                "description": "Automatically sets this generated profile variant as your default Dispatcharr target."
            }
        ]
        
        self.actions = [
            {
                "id": "generate_profile", "label": "Generate and Overwrite Profile",
                "button_label": "Apply & Synchronize Stream Profile", "button_color": "green",
                "description": "Overwrites any old variants and creates your single selected profile.",
                "confirm": {"required": True, "title": "Overwrite active stream configuration?",
                            "message": "This will safely replace previous variants to keep your setup clean."}
            },
            {
                "id": "reinstall", "label": "Reinstall Scripts",
                "button_label": "Refresh Local Executables", "button_color": "blue",
                "description": "Re-copy all target execution shell mappings and core supervisions."
            },
        ]

    def _all_files(self):
        return [SUPERVISOR] + [v[0] for v in PROFILES.values()]

    def _dst_file(self, filename): return f"{self.dst_dir}/{filename}"
    def _src_file(self, filename): return self.plugin_dir / filename

    def _read_installed_version(self):
        try: return self._parse_version((Path(self.dst_dir) / ".installed_version").read_text().strip())
        except OSError: return None

    def _install(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        # Dynamically distribute supervisor python engine and dynamically map shell executors
        for filename in self._all_files():
            dst = Path(self._dst_file(filename))
            if filename.endswith(".sh"):
                key_match = "passthrough"
                for k, v in PROFILES.items():
                    if v[0] == filename:
                        key_match = k
                        break
                dst.write_text(f'#!/bin/sh\nSCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec python3 "$SCRIPT_DIR/{SUPERVISOR}" {key_match} "$1" "$2"\n')
            else:
                shutil.copy2(self._src_file(SUPERVISOR), dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        with contextlib.suppress(OSError):
            (Path(self.dst_dir) / ".installed_version").write_text(self.version + "\n")

    @staticmethod
    def _valid_profile_name(name):
        return bool(name) and bool(re.match(r"^[\w .\-]{1,64}$", name))

    def _generate_profile(self):
        base_name = (self.settings.get("profile_name") or "Profilarr").strip()
        if not self._valid_profile_name(base_name):
            return {"status": "error", "message": "Profile prefix must be 1-64 chars, letters/digits/space/.-_ only."}
            
        selected_key = self.settings.get("selected_profile", "passthrough")
        filename, label, _, _ = PROFILES[selected_key]
        
        # Explicitly append the corresponding filename to the target stream profile object name
        target_profile_name = f"{base_name} Profile ({filename})"

        # DESTRUCTIVE OVERWRITE LOGIC: Purge any old iterations containing the prefix to ensure zero clutter
        existing_profiles = StreamProfile.objects.filter(name__icontains=base_name)
        for old_prof in existing_profiles:
            if not old_prof.locked:
                old_prof.delete()

        # Build the chosen profile configuration
        defaults = {
            "command": self._dst_file(filename),
            "parameters": "'{userAgent}' '{streamUrl}'",
            "is_active": True,
            "locked": False
        }
        
        new_profile = StreamProfile(name=target_profile_name, **defaults)
        new_profile.save()

        msg = f"Successfully synchronized stream pipeline. Active variant: {label}."
        
        if self.settings.get("set_as_default", True):
            try:
                from core.models import CoreSettings
                CoreSettings._update_group("stream_settings", "Stream Settings", {"default_stream_profile": new_profile.id})
                msg += f" Marked '{target_profile_name}' as global system default."
            except Exception as e:
                msg += f" (Could not prioritize profile automatically: {type(e).__name__}: {e})"
                
        return {"status": "ok", "message": msg}

    def _reinstall(self):
        try:
            self._install()
            return {"status": "ok", "message": "All execution layers refreshed successfully."}
        except OSError as e:
            return {"status": "error", "message": f"Refresh failed: {type(e).__name__}: {e}"}

    def stop(self, context):
        run_dir = Path(self.dst_dir) / "run"
        with contextlib.suppress(OSError):
            for pid_file in run_dir.glob("*.pid"):
                with contextlib.suppress(OSError, ValueError):
                    os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)

    def run(self, action: str, params: dict, context: dict):
        self.settings = context.get("settings", {}) or {}
        if action == "generate_profile": return self._generate_profile()
        if action == "reinstall": return self._reinstall()
        return {"status": "error", "message": f"Unknown action: {action}"}

