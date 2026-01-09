#!/usr/bin/env python3
"""
Hardware monitoring module for LLM performance benchmarking.

Provides comprehensive system resource monitoring including:
- RAM usage (baseline, peak, delta)
- CPU utilization (overall and per-core)
- Ollama process tracking
- Platform detection (Desktop vs Raspberry Pi)
"""

import psutil
import subprocess
import time
import platform
from typing import Optional, Dict, List, Tuple


class HardwareMonitor:
    """Monitor system resources during LLM inference"""

    def __init__(self):
        """Initialize hardware monitor"""
        self.ollama_process: Optional[psutil.Process] = None
        self.platform_info = self._detect_platform()

    def _detect_platform(self) -> Dict[str, str]:
        """
        Detect current platform (Desktop x86 vs Raspberry Pi ARM)

        Returns:
            Dict with platform details
        """
        machine = platform.machine().lower()
        system = platform.system()

        if 'arm' in machine or 'aarch64' in machine:
            platform_name = "Raspberry Pi 5"
            arch = "ARM64"
        elif 'x86_64' in machine or 'amd64' in machine:
            platform_name = "Desktop"
            arch = "x86_64"
        else:
            platform_name = "Unknown"
            arch = machine

        return {
            'name': platform_name,
            'arch': arch,
            'system': system,
            'cpu_count': psutil.cpu_count(logical=True),
            'cpu_count_physical': psutil.cpu_count(logical=False),
            'total_ram_gb': round(psutil.virtual_memory().total / (1024**3), 2)
        }

    def find_ollama_process(self) -> Optional[psutil.Process]:
        """
        Find the running Ollama server process

        Returns:
            psutil.Process object for Ollama, or None if not found
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if process name contains 'ollama'
                if proc.info['name'] and 'ollama' in proc.info['name'].lower():
                    # Verify it's the server (not a client command)
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'serve' in ' '.join(cmdline).lower():
                        self.ollama_process = psutil.Process(proc.info['pid'])
                        return self.ollama_process

                # Also check if just 'ollama' binary running
                if proc.info['name'] == 'ollama':
                    self.ollama_process = psutil.Process(proc.info['pid'])
                    return self.ollama_process

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return None

    def get_baseline_memory(self) -> Dict[str, float]:
        """
        Get current memory usage as baseline (before model load)

        Returns:
            Dict with memory metrics in MB
        """
        if not self.ollama_process:
            self.find_ollama_process()

        if not self.ollama_process:
            return {'rss_mb': 0.0, 'vms_mb': 0.0, 'available': False}

        try:
            mem_info = self.ollama_process.memory_info()
            return {
                'rss_mb': round(mem_info.rss / (1024**2), 2),  # Resident Set Size
                'vms_mb': round(mem_info.vms / (1024**2), 2),  # Virtual Memory Size
                'percent': round(self.ollama_process.memory_percent(), 2),
                'available': True
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {'rss_mb': 0.0, 'vms_mb': 0.0, 'available': False}

    def measure_memory_delta(self, baseline: Dict[str, float]) -> Dict[str, float]:
        """
        Measure memory increase from baseline

        Args:
            baseline: Previous baseline memory measurement

        Returns:
            Dict with current memory and delta from baseline
        """
        current = self.get_baseline_memory()

        if not current['available'] or not baseline.get('available'):
            return {
                'current_rss_mb': 0.0,
                'delta_rss_mb': 0.0,
                'available': False
            }

        return {
            'current_rss_mb': current['rss_mb'],
            'current_vms_mb': current['vms_mb'],
            'delta_rss_mb': round(current['rss_mb'] - baseline['rss_mb'], 2),
            'delta_vms_mb': round(current['vms_mb'] - baseline['vms_mb'], 2),
            'baseline_rss_mb': baseline['rss_mb'],
            'available': True
        }

    def measure_cpu_usage(self, duration: float = 1.0, per_core: bool = True) -> Dict[str, any]:
        """
        Measure CPU usage during inference

        Args:
            duration: Time to sample CPU (seconds)
            per_core: Whether to include per-core breakdown

        Returns:
            Dict with CPU metrics
        """
        if not self.ollama_process:
            self.find_ollama_process()

        if not self.ollama_process:
            return {'average': 0.0, 'available': False}

        try:
            # Initialize CPU measurement (first call always returns 0.0)
            self.ollama_process.cpu_percent(interval=None)

            # Sample system-wide per-core CPU at start
            if per_core:
                cpu_start = psutil.cpu_percent(interval=None, percpu=True)

            # Wait and measure process CPU
            time.sleep(max(0.1, duration))  # Minimum 0.1s for accuracy
            process_cpu = self.ollama_process.cpu_percent(interval=None)

            # Sample system-wide per-core CPU at end
            if per_core:
                cpu_end = psutil.cpu_percent(interval=None, percpu=True)
                # Calculate average per-core usage during interval
                per_core_usage = [round((start + end) / 2, 2)
                                 for start, end in zip(cpu_start, cpu_end)]
            else:
                per_core_usage = []

            return {
                'average': round(process_cpu, 2),
                'per_core': per_core_usage if per_core else [],
                'cpu_count': self.platform_info['cpu_count'],
                'available': True
            }

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {'average': 0.0, 'available': False}

    def get_ollama_running_models(self) -> List[str]:
        """
        Get list of currently loaded models via 'ollama ps'

        Returns:
            List of model names currently loaded
        """
        try:
            result = subprocess.run(
                ['ollama', 'ps'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            # Parse output (skip header line)
            lines = result.stdout.strip().split('\n')[1:]
            models = []

            for line in lines:
                if line.strip():
                    # First column is model name
                    parts = line.split()
                    if parts:
                        models.append(parts[0])

            return models

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def stop_model(self, model_name: str) -> bool:
        """
        Unload a specific model from memory

        Args:
            model_name: Name of model to unload

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                ['ollama', 'stop', model_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def create_snapshot(self, label: str = "snapshot", duration: float = 1.0) -> Dict:
        """
        Create a comprehensive snapshot of all metrics

        Args:
            label: Description of this snapshot
            duration: CPU sampling duration

        Returns:
            Dict with all available metrics
        """
        memory = self.get_baseline_memory()
        cpu = self.measure_cpu_usage(duration=duration, per_core=True)
        running_models = self.get_ollama_running_models()

        return {
            'label': label,
            'timestamp': time.time(),
            'platform': self.platform_info,
            'memory': memory,
            'cpu': cpu,
            'running_models': running_models,
            'ollama_pid': self.ollama_process.pid if self.ollama_process else None
        }

    def get_platform_name(self) -> str:
        """Get human-readable platform name"""
        return self.platform_info['name']

    def print_platform_info(self):
        """Print platform information"""
        info = self.platform_info
        print(f"\n{'='*60}")
        print(f"Platform Information")
        print(f"{'='*60}")
        print(f"Name:        {info['name']}")
        print(f"Architecture: {info['arch']}")
        print(f"System:      {info['system']}")
        print(f"CPU Cores:   {info['cpu_count']} logical ({info['cpu_count_physical']} physical)")
        print(f"Total RAM:   {info['total_ram_gb']} GB")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    # Test the hardware monitor
    print("🧪 Testing Hardware Monitor\n")

    monitor = HardwareMonitor()
    monitor.print_platform_info()

    # Find Ollama process
    print("🔍 Finding Ollama process...")
    ollama_proc = monitor.find_ollama_process()
    if ollama_proc:
        print(f"✅ Found Ollama (PID: {ollama_proc.pid})\n")
    else:
        print("❌ Ollama process not found\n")
        exit(1)

    # Get baseline memory
    print("📊 Measuring baseline memory...")
    baseline = monitor.get_baseline_memory()
    print(f"RSS: {baseline['rss_mb']} MB")
    print(f"VMS: {baseline['vms_mb']} MB\n")

    # Measure CPU
    print("💻 Measuring CPU usage (1 second sample)...")
    cpu = monitor.measure_cpu_usage(duration=1.0, per_core=True)
    print(f"Process CPU: {cpu['average']}%")
    if cpu['per_core']:
        print(f"Per-core: {cpu['per_core']}\n")

    # Check running models
    print("🔍 Checking running models...")
    models = monitor.get_ollama_running_models()
    if models:
        print(f"Running: {', '.join(models)}\n")
    else:
        print("No models currently loaded\n")

    # Create snapshot
    print("📸 Creating comprehensive snapshot...")
    snapshot = monitor.create_snapshot(label="test", duration=0.5)
    print(f"Snapshot captured at {snapshot['timestamp']}")
    print(f"Platform: {snapshot['platform']['name']}")
    print(f"Memory: {snapshot['memory']['rss_mb']} MB")
    print(f"CPU: {snapshot['cpu']['average']}%")

    print("\n✅ Hardware monitor test complete!")
