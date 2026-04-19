"""
Telemetry module for TalkingBuddy.

Provides:
  - setup_session_log()   : tees stdout to a timestamped .log file
  - TelemetryMonitor      : background thread that samples hardware every 30s
  - ilog(component, msg)  : structured [HH:MM:SS] [COMPONENT] log lines
"""

import os
import subprocess
import sys
import threading
import time
from datetime import datetime


# ── Tee ───────────────────────────────────────────────────────────────────────

class _Tee:
    """Writes to multiple streams simultaneously (terminal + log file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    # Proxy attribute lookups to the first stream (terminal) so Flask/Werkzeug
    # can call e.g. sys.stdout.fileno() without crashing.
    def __getattr__(self, name):
        return getattr(self._streams[0], name)


_log_file = None  # open file handle, kept alive for the session


def setup_session_log(base_dir: str) -> str:
    """
    Creates a timestamped log file and installs a tee so every print() call
    is written to both the terminal and the log file.

    Returns the path of the created log file.
    """
    global _log_file

    os.makedirs(base_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(base_dir, f"session_{timestamp}.log")

    _log_file = open(log_path, "w", buffering=1, encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, _log_file)

    # Session header
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"\n{'=' * 60}\n"
        f"SESSION: {now_str}  |  TalkingBuddy\n"
        f"{'=' * 60}\n"
    )
    print(header, end="")
    return log_path


# ── Structured log helper ─────────────────────────────────────────────────────

def ilog(component: str, msg: str):
    """Print a structured timestamped log line, captured by the tee."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{component:9s}] {msg}", flush=True)


# ── Hardware sampler ──────────────────────────────────────────────────────────

def _cpu_temp() -> str:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return f"{int(f.read().strip()) / 1000:.1f}°C"
    except Exception:
        return "N/A"


def _ram_info() -> str:
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                if k in ("MemTotal", "MemAvailable"):
                    mem[k] = int(v.split()[0]) // 1024  # kB → MB
        return f"{mem.get('MemAvailable', 0)}/{mem.get('MemTotal', 0)}MB"
    except Exception:
        return "N/A"


def _throttle_status() -> str:
    try:
        r = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=3
        )
        val = int(r.stdout.strip().split("=")[1], 16)
        currently = bool(val & 0x4)    # bit 2: currently throttled
        occurred  = bool(val & 0x40000)  # bit 18: throttling has occurred
        if currently:
            return "⚠️  SIM (throttling ativo)"
        if occurred:
            return "⚠️  Ocorreu (não ativo agora)"
        return "No"
    except Exception:
        return "N/A"


class TelemetryMonitor:
    """
    Background daemon thread that logs hardware metrics every `interval` seconds.
    Pass the battery_monitor instance from app.py (may be None).
    """

    def __init__(self, battery_monitor=None, interval: int = 30):
        self._battery = battery_monitor
        self._interval = interval
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="TelemetryMonitor"
        )

    def start(self):
        self._thread.start()

    def _battery_info(self) -> str:
        if not self._battery:
            return "N/A"
        try:
            data = self._battery.read()
            if not data.get("available"):
                return "unavailable"
            v    = data.get("voltage", 0)
            soc  = data.get("soc", 0)
            chg  = data.get("charging")
            chg_str = "charging=True" if chg else ("charging=False" if chg is False else "charging=?")
            # Warn if voltage below healthy LiPo floor
            flag = " ⚠️ LOW VOLTAGE" if v < 3.6 else ""
            return f"{v:.2f}V {soc:.0f}% {chg_str}{flag}"
        except Exception:
            return "error"

    def _loop(self):
        # Initial short delay to let the app finish booting before first sample
        time.sleep(10)
        while True:
            try:
                ilog(
                    "TELEMETRY",
                    f"CPU: {_cpu_temp()} | RAM: {_ram_info()} | "
                    f"Battery: {self._battery_info()} | Throttled: {_throttle_status()}"
                )
            except Exception as e:
                ilog("TELEMETRY", f"Erro ao amostrar: {e}")
            time.sleep(self._interval)
