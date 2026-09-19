#!/usr/bin/env python3
"""Profilarr process supervisor.

The supervisor is the process launched by Dispatcharr. Linux PR_SET_PDEATHSIG
makes the supervisor and its ffmpeg/cvlc children receive SIGKILL when the
Dispatcharr-launched supervisor is killed, including SIGKILL where shell traps
cannot run.
"""
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
        time.sleep(.05)
    if proc.poll() is None:
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass


def ffmpeg_cmd(profile, ua, url):
    # Core ingestion variables optimized for low latency and smooth recovery
    c = ["ffmpeg", "-user_agent", ua,
         "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
         "-reconnect_delay_max", "5", "-multiple_requests", "1", "-seekable", "0",
         "-fflags", "+discardcorrupt+genpts+igndts", 
         "-probesize", "10M", 
         "-analyzeduration", "5M", 
         "-i", url, "-map", "0:v:0?", "-map", "0:a?", "-sn", "-dn"]
    
    # --- 1. Video and Audio Encoding Profiles ---
    
    # [DEFAULT PASSTHROUGH PROFILE]
    if profile == "passthrough":
        c += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
        
    # [NVIDIA NVENC ENCODING PROFILES]
    elif profile == "uncapped":
        c += ["-c:v", "h264_nvenc", "-preset", "p4", "-profile:v", "high", "-pix_fmt", "yuv420p", "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
    elif profile == "fps30":
        c += ["-vf", "fps=30000/1001", "-fps_mode", "cfr", "-c:v", "h264_nvenc", "-preset", "p4", "-profile:v", "high", "-pix_fmt", "yuv420p", "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
    elif profile == "fps60":
        c += ["-vf", "fps=60000/1001", "-fps_mode", "cfr", "-c:v", "h264_nvenc", "-preset", "p4", "-profile:v", "high", "-pix_fmt", "yuv420p", "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "120", "-keyint_min", "120", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
        
    # [CPU SOFTWARE ENCODING PROFILES (LIBX264 EQUIVALENTS)]
    elif profile == "cpu_uncapped":
        c += ["-c:v", "libx264", "-preset", "superfast", "-tune", "zerolatency", "-profile:v", "high", "-pix_fmt", "yuv420p", "-x264-params", "nal-hrd=cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
    elif profile == "cpu_fps30":
        c += ["-vf", "fps=30000/1001", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "superfast", "-tune", "zerolatency", "-profile:v", "high", "-pix_fmt", "yuv420p", "-x264-params", "nal-hrd=cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
    elif profile == "cpu_fps60":
        c += ["-vf", "fps=60000/1001", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "superfast", "-tune", "zerolatency", "-profile:v", "high", "-pix_fmt", "yuv420p", "-x264-params", "nal-hrd=cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M", "-g", "120", "-keyint_min", "120", "-sc_threshold", "0", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-async", "1"]
        
    else:
        raise SystemExit("unknown profile identifier: " + profile)
    
    # 2. Perfect MPEG-TS flags for Emby Ingestion
    c += [
        "-mpegts_copyts", "0", 
        "-avoid_negative_ts", "make_zero", 
        "-muxdelay", "0", 
        "-muxpreload", "0", 
        "-max_muxing_queue_size", "4096", 
        "-flush_packets", "1", 
        "-mpegts_flags", "+pat_pmt_at_frames+resend_headers", 
        "-f", "mpegts", 
        "pipe:1"
    ]
    return c


def cvlc_cmd():
    return ["cvlc", "-I", "dummy", "--no-lua", "--no-auto-preparse", "--no-dbus", "--no-interact", "--no-stats", "--aout", "adummy", "--vout", "vdummy", "--no-sout-all", "--sout-keep", "--network-caching", "3000", "--sout-mux-caching", "1500", "--adaptive-logic=highest", '--sout=#std{access=file,mux=ts,dst=-}', "fd://0"]


def main():
    if len(sys.argv) != 4:
        print("usage: profilarr-supervisor.py <profile_key> <userAgent> <streamUrl>", file=sys.stderr)
        return 2
    profile, ua, url = sys.argv[1:]
    set_pdeathsig()
    run_dir = Path("/data/profilarr/run")
    run_dir.mkdir(parents=True, exist_ok=True)
    pidfile = run_dir / f"{os.getpid()}.pid"
    pidfile.write_text(str(os.getpid()) + "\n")
    ffmpeg = cvlc = None
    def shutdown(signum, frame):
        terminate(cvlc); terminate(ffmpeg)
        try: pidfile.unlink()
        except FileNotFoundError: pass
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        ffmpeg = subprocess.Popen(ffmpeg_cmd(profile, ua, url), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=None, start_new_session=True, preexec_fn=child_setup, close_fds=True)
        cvlc = subprocess.Popen(cvlc_cmd(), stdin=ffmpeg.stdout, stdout=sys.stdout, stderr=None, start_new_session=True, preexec_fn=child_setup, close_fds=True)
        ffmpeg.stdout.close()
        while True:
            if cvlc.poll() is not None:
                terminate(ffmpeg); return cvlc.returncode
            if ffmpeg.poll() is not None:
                terminate(cvlc); return ffmpeg.returncode
            time.sleep(.25)
    finally:
        terminate(cvlc); terminate(ffmpeg)
        try: pidfile.unlink()
        except FileNotFoundError: pass

if __name__ == "__main__":
    raise SystemExit(main())

