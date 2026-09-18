"""Profilarr Dispatcharr plugin.

Installs the four stream scripts plus the bundled supervisor into
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

PROFILES = {
    "passthrough": ("profilarr.sh", "Passthrough (base)", "Video passthrough (-c:v copy, no re-encode) | cvlc."),
    "uncapped": ("profilarr-uncapped.sh", "Uncapped FPS", "NVENC re-encode at 8Mbps CBR with source frame rate preserved | cvlc."),
    "fps30": ("profilarr-30fps-capped.sh", "30 FPS Capped", "NVENC re-encode forced to 29.97fps | cvlc."),
    "fps60": ("profilarr-60fps-forced.sh", "60 FPS Forced (With Frame Duplication)", "NVENC re-encode forced to 59.94fps | cvlc."),
}
SUPERVISOR = "profilarr-supervisor.py"

class Plugin:
    name = "Profilarr"
    version = "1.0.6"
    description = "Hybrid ffmpeg + cvlc stream profile with 4 selectable variants and bundled process supervision."
    author = "Tw1zT3d2four7"
    help_url = "https://github.com/Tw1zT3d2four7/Profilarr"
    dst_dir = "/data/profilarr"
    plugin_dir = Path(__file__).resolve().parent
    plugin_key = plugin_dir.name.replace(" ", "_").lower()

    @staticmethod
    def _parse_version(s):
        if not s:
            return None
        try:
            return tuple(int(x) for x in s.strip().lstrip("v").split("."))
        except (ValueError, AttributeError):
            return None

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

        self.fields = [{
            "id": "profile_name", "label": "Profile Name *", "type": "string",
            "default": "Profilarr",
            "description": "Base name used for generated Dispatcharr Stream Profiles."
        }]
        for key, (filename, label, desc) in PROFILES.items():
            self.fields.append({
                "id": f"enable_{key}", "label": f"Enable '{label}' ({filename})",
                "type": "boolean", "default": key == "passthrough", "description": desc
            })
            self.fields.append({
                "id": f"default_{key}",
                "label": f"Set '{label}' ({filename}) as default Stream Profile",
                "type": "boolean", "default": False,
                "description": "Tick on at most one enabled profile."
            })
        self.fields.append({
            "id": "next_steps", "label": "After you click Generate", "type": "info",
            "description": "Refresh Dispatcharr in your browser after generating profiles."
        })
        self.actions = [
            {
                "id": "generate_profile", "label": "Generate Stream Profiles",
                "button_label": "Generate Stream Profiles", "button_color": "green",
                "description": "Create/update enabled Profilarr Stream Profiles.",
                "confirm": {"required": True, "title": "Create/update Profilarr Stream Profiles?",
                            "message": "Refresh Dispatcharr in your browser after this completes."}
            },
            {
                "id": "reinstall", "label": "Reinstall scripts",
                "button_label": "Reinstall all Profilarr files", "button_color": "blue",
                "description": "Re-copy all four scripts and the bundled supervisor."
            },
        ]

    def _all_files(self):
        return [SUPERVISOR] + [v[0] for v in PROFILES.values()]

    def _dst_file(self, filename):
        return f"{self.dst_dir}/{filename}"

    def _src_file(self, filename):
        return self.plugin_dir / filename

    def _read_installed_version(self):
        try:
            return self._parse_version((Path(self.dst_dir) / ".installed_version").read_text().strip())
        except OSError:
            return None

    def _install(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        for filename in self._all_files():
            src = self._src_file(filename)
            dst = Path(self._dst_file(filename))
            shutil.copy2(src, dst)
            st = os.stat(dst)
            os.chmod(dst, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        with contextlib.suppress(OSError):
            (Path(self.dst_dir) / ".installed_version").write_text(self.version + "\n")

    @staticmethod
    def _valid_profile_name(name):
        return bool(name) and bool(re.match(r"^[\w .\-]{1,64}$", name))

    def _generate_profile(self):
        base_name = (self.settings.get("profile_name") or "Profilarr").strip()
        if not self._valid_profile_name(base_name):
            return {"status": "error", "message": "Profile name must be 1-64 chars, letters/digits/space/.-_ only."}
        default_keys = [k for k in PROFILES if self.settings.get(f"default_{k}") and self.settings.get(f"enable_{k}", k == "passthrough")]
        if len(default_keys) > 1:
            return {"status": "error", "message": f"Only one profile can be set as default — currently ticked: {', '.join(default_keys)}."}
        if not all(os.path.isfile(self._dst_file(f)) for f in self._all_files()):
            self._install()
        created, updated, skipped = [], [], []
        profile_by_key = {}
        for key, (filename, label, _) in PROFILES.items():
            enabled = self.settings.get(f"enable_{key}", key == "passthrough")
            if not enabled:
                skipped.append(label); continue
            name = f"{base_name} - {filename}"
            if not self._valid_profile_name(name):
                return {"status": "error", "message": f"Generated profile name '{name}' is invalid (1-64 chars, letters/digits/space/.-_ only)."}
            defaults = {"command": self._dst_file(filename), "parameters": "'{userAgent}' '{streamUrl}'", "is_active": True, "locked": False}
            existing = StreamProfile.objects.filter(name__iexact=name).first()
            if existing:
                if existing.locked:
                    return {"status": "error", "message": f"Profile '{name}' exists and is locked — pick a different Profile Name."}
                for k, v in defaults.items(): setattr(existing, k, v)
                existing.save(); profile_by_key[key] = existing; updated.append(name)
            else:
                profile = StreamProfile(name=name, **defaults); profile.save(); profile_by_key[key] = profile; created.append(name)
        msg = []
        if created: msg.append("Created: " + ", ".join(created))
        if updated: msg.append("Updated: " + ", ".join(updated))
        if skipped: msg.append("Not enabled (skipped): " + ", ".join(skipped))
        if default_keys:
            try:
                from core.models import CoreSettings
                CoreSettings._update_group("stream_settings", "Stream Settings", {"default_stream_profile": profile_by_key[default_keys[0]].id})
                msg.append(f"Set '{profile_by_key[default_keys[0]].name}' as default Stream Profile")
            except Exception as e:
                msg.append(f"(could not set default: {type(e).__name__}: {e})")
        msg.append("Refresh Dispatcharr in your browser to see the change.")
        return {"status": "ok", "message": ". ".join(msg)}

    def _reinstall(self):
        try:
            self._install()
            return {"status": "ok", "message": f"Reinstalled all Profilarr files into {self.dst_dir}/"}
        except OSError as e:
            return {"status": "error", "message": f"Install failed: {type(e).__name__}: {e}"}

    def stop(self, context):
        """Terminate supervisors started by this plugin when it is stopped/reloaded."""
        run_dir = Path(self.dst_dir) / "run"
        try:
            for pid_file in run_dir.glob("*.pid"):
                try:
                    pid = int(pid_file.read_text().strip())
                    os.kill(pid, signal.SIGTERM)
                except (OSError, ValueError):
                    pass
        except OSError:
            pass

    def run(self, action: str, params: dict, context: dict):
        self.settings = context.get("settings", {}) or {}
        if action == "generate_profile": return self._generate_profile()
        if action == "reinstall": return self._reinstall()
        return {"status": "error", "message": f"Unknown action: {action}"}
