#!/usr/bin/env python3
"""Profilarr 2.0.4 process supervisor.

The supervisor is the process launched by Dispatcharr. Linux PR_SET_PDEATHSIG
makes the supervisor and its ffmpeg/cvlc children receive SIGKILL when the
Dispatcharr-launched supervisor is killed, including SIGKILL where shell
traps cannot run.
"""
from __future__ import annotations
import ctypes
import ctypes.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PR_SET_PDEATHSIG = 1
libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

VIDEO_ENGINES = {
    "copy": ("copy", "none"),
    "h264_nvenc": ("h264_nvenc", "nvenc"),
    "hevc_nvenc": ("hevc_nvenc", "nvenc"),
    "av1_nvenc": ("av1_nvenc", "nvenc"),
    "h264_amf": ("h264_amf", "amf"),
    "hevc_amf": ("hevc_amf", "amf"),
    "av1_amf": ("av1_amf", "amf"),
    "h264_qsv": ("h264_qsv", "qsv"),
    "hevc_qsv": ("hevc_qsv", "qsv"),
    "av1_qsv": ("av1_qsv", "qsv"),
    "libx264": ("libx264", "cpu"),
    "libx265": ("libx265", "cpu"),
    "libsvtav1": ("libsvtav1", "cpu"),
}

AUDIO_ENCODERS = {
    "copy": ("copy", None),
    "aac": ("aac", "192k"),
    "ac3": ("ac3", "192k"),
    "eac3": ("eac3", "192k"),
    "opus": ("libopus", "128k"),
    "mp3": ("libmp3lame", "192k"),
}

ALLOWED = {
    "default": {"copy"},
    "nvidia": {"copy", "h264_nvenc", "hevc_nvenc", "av1_nvenc"},
    "amd": {"copy", "h264_amf", "hevc_amf", "av1_amf"},
    "intel": {"copy", "h264_qsv", "hevc_qsv", "av1_qsv"},
    "cpu": {"copy", "libx264", "libx265", "libsvtav1"},
}


def set_pdeathsig():
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    if os.getppid() == 1:
        os.kill(os.getpid(), signal.SIGKILL)


def child_setup():
    set_pdeathsig()


def terminate(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def video_args(v):
    enc, family = VIDEO_ENGINES[v]
    if enc == "copy":
        return ["-c:v", "copy"]
    args = ["-c:v", enc]
    if family == "nvenc":
        args += ["-preset", "p4", "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M"]
    elif family == "amf":
        args += ["-quality", "balanced", "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M"]
    elif family == "qsv":
        args += ["-preset", "veryfast", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M"]
    elif family == "cpu":
        args += ["-preset", "superfast", "-tune", "zerolatency", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M"]
    if enc.startswith("h264_") or enc == "libx264":
        args += ["-profile:v", "high", "-pix_fmt", "yuv420p"]
    elif enc.startswith("hevc_") or enc == "libx265":
        args += ["-pix_fmt", "yuv420p"]
    return args


def audio_args(a):
    enc, br = AUDIO_ENCODERS[a]
    out = ["-c:a", enc]
    if br:
        out += ["-b:a", br, "-ac", "2"]
    return out


def ffmpeg_cmd(profile, ua, url, video, audio):
    if profile not in ALLOWED:
        raise ValueError("unknown profile identifier: " + profile)
    if video not in ALLOWED[profile]:
        raise ValueError(f"video override '{video}' is invalid for profile '{profile}'")
    if audio not in AUDIO_ENCODERS:
        raise ValueError("unknown audio override: " + audio)

    c = [
        "ffmpeg", "-hide_banner", "-user_agent", ua,
        "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5", "-multiple_requests", "1", "-seekable", "0",
        "-fflags", "+discardcorrupt+genpts+igndts",
        "-probesize", "10M", "-analyzeduration", "5M", "-i", url,
        "-map", "0:v:0?", "-map", "0:a:0?", "-sn", "-dn",
    ]
    c += video_args(video)
    c += audio_args(audio)
    c += [
        "-mpegts_copyts", "0", "-avoid_negative_ts", "make_zero",
        "-muxdelay", "0", "-muxpreload", "0", "-max_muxing_queue_size", "4096",
        "-flush_packets", "1",
        "-mpegts_flags", "+pat_pmt_at_frames+resend_headers+initial_discontinuity",
        "-f", "mpegts", "pipe:1",
    ]
    return c


def cvlc_cmd():
    return [
        "cvlc", "-I", "dummy", "--no-lua", "--no-auto-preparse", "--no-dbus",
        "--no-interact", "--no-stats", "--aout", "adummy", "--vout", "vdummy",
        "--no-sout-all", "--sout-keep", "--network-caching", "6000",
        "--sout-mux-caching", "1500", "--adaptive-logic=highest",
        "--sout=#std{access=file,mux=ts,dst=-}", "fd://0",
    ]


def main():
    if len(sys.argv) != 6:
        print("usage: profilarr-supervisor.py <profile_key> <userAgent> <streamUrl> <videoOverride> <audioOverride>", file=sys.stderr)
        return 2

    profile, ua, url, video, audio = sys.argv[1:]
    try:
        set_pdeathsig()
        run_dir = Path("/data/profilarr/run")
        run_dir.mkdir(parents=True, exist_ok=True)
        pidfile = run_dir / f"{os.getpid()}.pid"
        pidfile.write_text(str(os.getpid()) + "\n")
        ffmpeg = cvlc = None

        def shutdown(signum, frame):
            terminate(cvlc)
            terminate(ffmpeg)
            try:
                pidfile.unlink()
            except FileNotFoundError:
                pass
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        try:
            ffmpeg = subprocess.Popen(
                ffmpeg_cmd(profile, ua, url, video, audio),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=None,
                start_new_session=True,
                preexec_fn=child_setup,
                close_fds=True,
            )
            cvlc = subprocess.Popen(
                cvlc_cmd(),
                stdin=ffmpeg.stdout,
                stdout=sys.stdout,
                stderr=None,
                start_new_session=True,
                preexec_fn=child_setup,
                close_fds=True,
            )
            ffmpeg.stdout.close()
            while True:
                if cvlc.poll() is not None:
                    terminate(ffmpeg)
                    return cvlc.returncode
                if ffmpeg.poll() is not None:
                    terminate(cvlc)
                    return ffmpeg.returncode
                time.sleep(0.25)
        finally:
            terminate(cvlc)
            terminate(ffmpeg)
            try:
                pidfile.unlink()
            except FileNotFoundError:
                pass
    except (ValueError, OSError) as e:
        print(f"[Profilarr] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
