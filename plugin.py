"""Profilarr Dispatcharr plugin.

Installs profilarr.sh, profilarr-uncapped.sh, profilarr-30fps-capped.sh and
profilarr-60fps-forced.sh into /data/profilarr/ on first load (and on
upgrades). Each is a standalone POSIX-sh pipeline:

  passthrough : ffmpeg (fetch, -c:v copy, regen timestamps) | cvlc (buffer)
  uncapped    : passthrough pipeline | ffmpeg (NVENC re-encode, source FPS kept)
  fps30       : passthrough pipeline | ffmpeg (NVENC re-encode, forced 29.97fps)
  fps60       : passthrough pipeline | ffmpeg (NVENC re-encode, forced 59.94fps,
                frame duplication on lower-FPS sources)

"Generate Stream Profiles" creates/updates one Dispatcharr StreamProfile per
enabled variant and, if exactly one Set as default toggle is ticked, makes
that one the instance-wide default. There are no environment-variable
knobs — every setting is hardcoded in the relevant profilarr*.sh. Edit the
script directly and use "Reinstall scripts" to push the change.
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import stat
from pathlib import Path

from apps.plugins.models import PluginConfig
from core.models import StreamProfile


# key -> (script filename, human-readable label for the settings UI, description)
# The generated StreamProfile is always named "<profile_name> - <filename>" so
# the name itself tells you exactly which script backs it.
PROFILES = {
    "passthrough": (
        "profilarr.sh",
        "Passthrough (base)",
        "Video passthrough (-c:v copy, no re-encode) | cvlc. Most stable, "
        "but can still show artifacting in some players on inconsistent-"
        "timestamp or changing-frame-rate fallback streams.",
    ),
    "uncapped": (
        "profilarr-uncapped.sh",
        "Uncapped FPS",
        "fetch | NVENC re-encode at 8Mbps CBR, source frame rate kept as-is "
        "(-g 60/-keyint_min 60) | cvlc. Base transcode profile.",
    ),
    "fps30": (
        "profilarr-30fps-capped.sh",
        "30 FPS Capped",
        "fetch | NVENC re-encode forced to 29.97fps (-vf fps=30000/1001, "
        "-fps_mode cfr) | cvlc. Higher-FPS sources get frames dropped.",
    ),
    "fps60": (
        "profilarr-60fps-forced.sh",
        "60 FPS Forced (With Frame Duplication)",
        "fetch | NVENC re-encode forced to 59.94fps (-vf fps=60000/1001, "
        "-fps_mode cfr) | cvlc. Lower-FPS sources get frames duplicated, "
        "not interpolated — not CPU harsh.",
    ),
}


class Plugin:
    name = "Profilarr"
    version = "1.0.4"
    description = (
        "Hybrid ffmpeg + cvlc stream profile with 4 selectable variants: a "
        "video-passthrough base and three NVENC transcode profiles "
        "(uncapped / 30fps-capped / 60fps-forced) chained after it."
    )
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

        if not all(os.path.isfile(self._dst_script(k)) for k in PROFILES):
            self._install()
        else:
            local = self._read_installed_version()
            packaged = self._parse_version(self.version)
            if packaged is not None and (local is None or packaged > local):
                self._install()

        self.fields = [
            {
                "id": "profile_name",
                "label": "Profile Name *",
                "type": "string",
                "default": "Profilarr",
                "description": "Base name shown in Dispatcharr's Stream Profile "
                               "picker. Each enabled profile is created as "
                               "'<this> - <script filename>.sh', so the name "
                               "itself always tells you which script it runs.",
            },
        ]
        for key, (filename, label, desc) in PROFILES.items():
            self.fields.append({
                "id": f"enable_{key}",
                "label": f"Enable '{label}' ({filename})",
                "type": "boolean",
                "default": key == "passthrough",
                "description": desc,
            })
            self.fields.append({
                "id": f"default_{key}",
                "label": f"Set '{label}' ({filename}) as default Stream Profile",
                "type": "boolean",
                "default": False,
                "description": "Tick on at most one enabled profile across "
                               "all four. Leave every one off to not change "
                               "the instance-wide default.",
            })
        self.fields.append({
            "id": "next_steps",
            "label": "After you click Generate",
            "type": "info",
            "description": "1) One Stream Profile per enabled variant appears "
                           "in Settings → Stream Settings → Profiles. 2) The "
                           "one variant (if any) with its 'Set as default' "
                           "ticked becomes the instance-wide default; "
                           "otherwise assign profiles per-channel under "
                           "Channels → Edit. 3) Tune a channel and check the "
                           "Dispatcharr transcode logs.",
        })
        self.fields.append({
            "id": "tuning_note",
            "label": "Tuning",
            "type": "info",
            "description": "There are no environment-variable knobs — every "
                           "setting (network-caching, ffmpeg flags, bitrate, "
                           "GOP size, etc.) is hardcoded directly in each "
                           "profilarr*.sh. To change behavior, edit the "
                           "relevant script in this plugin's folder and run "
                           "'Reinstall scripts' to push the change to "
                           "/data/profilarr/.",
        })

        self.actions = [
            {
                "id": "generate_profile",
                "label": "Generate Stream Profiles",
                "button_label": "Generate Stream Profiles",
                "button_color": "green",
                "description": "Create/update the Stream Profile for each "
                               "enabled variant and, if exactly one is "
                               "marked default, set it instance-wide.",
                "confirm": {
                    "required": True,
                    "title": "Create/update Profilarr Stream Profiles?",
                    "message": "Refresh Dispatcharr in your browser after "
                               "this completes for changes to appear in "
                               "the picker.",
                },
            },
            {
                "id": "reinstall",
                "label": "Reinstall scripts",
                "button_label": "Reinstall all profilarr*.sh",
                "button_color": "blue",
                "description": "Re-copy all four profilarr*.sh scripts into "
                               "/data/profilarr/ (useful after editing a "
                               "script or after a plugin update if the "
                               "install step was skipped).",
            },
        ]

    def _dst_script(self, key):
        filename, _, _ = PROFILES[key]
        return f"{self.dst_dir}/{filename}"

    def _src_script(self, key):
        filename, _, _ = PROFILES[key]
        return self.plugin_dir / filename

    def _read_installed_version(self):
        """Read the version stamped by the most recent _install() into
        <dst_dir>/.installed_version. None if missing or unparseable — the
        upgrade gate in __init__ treats that as "reinstall" (idempotent copy,
        always safe)."""
        sentinel = Path(self.dst_dir) / ".installed_version"
        try:
            return self._parse_version(sentinel.read_text().strip())
        except OSError:
            return None

    def _install(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        for key in PROFILES:
            src, dst = self._src_script(key), self._dst_script(key)
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
            return {"status": "error",
                    "message": "Profile name must be 1-64 chars, letters/digits/space/.-_ only."}

        default_keys = [
            k for k in PROFILES
            if self.settings.get(f"default_{k}") and self.settings.get(f"enable_{k}", k == "passthrough")
        ]
        if len(default_keys) > 1:
            return {"status": "error",
                    "message": "Only one profile can be set as default — "
                               f"currently ticked: {', '.join(default_keys)}."}

        if not all(os.path.isfile(self._dst_script(k)) for k in PROFILES):
            self._install()

        created, updated, skipped = [], [], []
        profile_by_key = {}

        for key, (filename, label, _) in PROFILES.items():
            enabled = self.settings.get(f"enable_{key}", key == "passthrough")
            if not enabled:
                skipped.append(label)
                continue

            name = f"{base_name} - {filename}"
            if not self._valid_profile_name(name):
                return {"status": "error",
                        "message": f"Generated profile name '{name}' is invalid "
                                   "(1-64 chars, letters/digits/space/.-_ only)."}

            defaults = {
                "command": self._dst_script(key),
                "parameters": "'{userAgent}' '{streamUrl}'",
                "is_active": True,
                "locked": False,
            }
            existing = StreamProfile.objects.filter(name__iexact=name).first()
            if existing:
                if existing.locked:
                    return {"status": "error",
                            "message": f"Profile '{name}' exists and is locked — "
                                       "pick a different Profile Name."}
                for k, v in defaults.items():
                    setattr(existing, k, v)
                existing.save()
                profile_by_key[key] = existing
                updated.append(name)
            else:
                profile = StreamProfile(name=name, **defaults)
                profile.save()
                profile_by_key[key] = profile
                created.append(name)

        msg_parts = []
        if created:
            msg_parts.append("Created: " + ", ".join(created))
        if updated:
            msg_parts.append("Updated: " + ", ".join(updated))
        if skipped:
            msg_parts.append("Not enabled (skipped): " + ", ".join(skipped))

        if default_keys:
            key = default_keys[0]
            try:
                from core.models import CoreSettings
                CoreSettings._update_group(
                    "stream_settings", "Stream Settings",
                    {"default_stream_profile": profile_by_key[key].id},
                )
                msg_parts.append(f"Set '{profile_by_key[key].name}' as default Stream Profile")
            except Exception as e:
                msg_parts.append(f"(could not set default: {type(e).__name__}: {e})")

        msg_parts.append("Refresh Dispatcharr in your browser to see the change.")
        return {"status": "ok", "message": ". ".join(msg_parts)}

    def _reinstall(self):
        try:
            self._install()
            return {"status": "ok",
                    "message": f"Reinstalled all profilarr*.sh scripts into {self.dst_dir}/"}
        except OSError as e:
            return {"status": "error",
                    "message": f"Install failed: {type(e).__name__}: {e}"}

    def run(self, action: str, params: dict, context: dict):
        self.settings = context.get("settings", {}) or {}
        if action == "generate_profile":
            return self._generate_profile()
        if action == "reinstall":
            return self._reinstall()
        return {"status": "error", "message": f"Unknown action: {action}"}
