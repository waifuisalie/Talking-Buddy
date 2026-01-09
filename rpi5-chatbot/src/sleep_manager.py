"""
Sleep Manager - Controls Ollama service for power management

Manages Ollama service lifecycle for deep sleep power savings:
- Light sleep: Keep Ollama running (model in RAM, fast wake)
- Deep sleep: Stop Ollama service (save power, slower wake)
"""

import subprocess
import time
import requests
from typing import Optional

class SleepManager:
    """Manages Ollama service for power-efficient sleep modes"""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        """
        Initialize sleep manager

        Args:
            ollama_url: Base URL for Ollama service
        """
        self.ollama_url = ollama_url
        self.is_ollama_running = False
        self._check_ollama_status()

    def _check_ollama_status(self) -> bool:
        """
        Check if Ollama service is currently running

        Returns:
            True if Ollama is responsive, False otherwise
        """
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            self.is_ollama_running = response.status_code == 200
            return self.is_ollama_running
        except requests.exceptions.RequestException:
            self.is_ollama_running = False
            return False

    def enter_deep_sleep(self) -> bool:
        """
        Enter deep sleep by stopping Ollama service

        Returns:
            True if successful, False otherwise
        """
        if not self.is_ollama_running:
            print("ℹ️  Ollama already stopped")
            return True

        try:
            print("💤 Entering deep sleep - Stopping Ollama service...")

            # Try user service first
            result = subprocess.run(
                ["systemctl", "--user", "stop", "ollama"],
                capture_output=True,
                text=True,
                timeout=10
            )

            # If user service doesn't exist, try system service
            if result.returncode != 0:
                result = subprocess.run(
                    ["sudo", "systemctl", "stop", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            if result.returncode == 0:
                # Wait for service to stop
                time.sleep(2)
                self._check_ollama_status()

                if not self.is_ollama_running:
                    print("✅ Deep sleep: Ollama service stopped")
                    return True
                else:
                    print("⚠️  Ollama still running after stop command")
                    return False
            else:
                print(f"❌ Failed to stop Ollama: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("❌ Timeout stopping Ollama service")
            return False
        except Exception as e:
            print(f"❌ Error entering deep sleep: {e}")
            return False

    def wake_from_deep_sleep(self, model_name: Optional[str] = None, timeout: float = 30.0) -> bool:
        """
        Wake from deep sleep by starting Ollama service

        Args:
            model_name: Optional model name to warm up after starting
            timeout: Maximum seconds to wait for Ollama to be ready

        Returns:
            True if successful, False otherwise
        """
        if self.is_ollama_running:
            print("ℹ️  Ollama already running")
            return True

        try:
            print("🌅 Waking from deep sleep - Starting Ollama service...")

            # Try user service first
            result = subprocess.run(
                ["systemctl", "--user", "start", "ollama"],
                capture_output=True,
                text=True,
                timeout=10
            )

            # If user service doesn't exist, try system service
            if result.returncode != 0:
                result = subprocess.run(
                    ["sudo", "systemctl", "start", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            if result.returncode != 0:
                print(f"❌ Failed to start Ollama: {result.stderr}")
                return False

            # Wait for Ollama to be ready
            print("⏳ Waiting for Ollama to be ready...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                if self._check_ollama_status():
                    elapsed = time.time() - start_time
                    print(f"✅ Ollama service started ({elapsed:.1f}s)")

                    # Optional: Warm up model
                    if model_name:
                        self._warm_up_model(model_name)

                    return True

                time.sleep(1)

            print(f"❌ Timeout waiting for Ollama to start ({timeout}s)")
            return False

        except subprocess.TimeoutExpired:
            print("❌ Timeout starting Ollama service")
            return False
        except Exception as e:
            print(f"❌ Error waking from deep sleep: {e}")
            return False

    def _warm_up_model(self, model_name: str) -> bool:
        """
        Warm up a model by making a test request

        Args:
            model_name: Name of the model to warm up

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"🔥 Warming up model: {model_name}...")

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "test",
                    "stream": False
                },
                timeout=15
            )

            if response.status_code == 200:
                print(f"✅ Model {model_name} ready")
                return True
            else:
                print(f"⚠️  Model warm-up returned status {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Error warming up model: {e}")
            return False

    def is_running(self) -> bool:
        """
        Check if Ollama is currently running

        Returns:
            True if running, False otherwise
        """
        return self._check_ollama_status()

    def get_status(self) -> dict:
        """
        Get current Ollama status

        Returns:
            Dictionary with status information
        """
        return {
            "ollama_running": self.is_ollama_running,
            "ollama_url": self.ollama_url
        }

def test_sleep_manager():
    """Test the sleep manager (WARNING: Will stop/start Ollama!)"""
    print("Testing Sleep Manager:")
    print("=" * 60)
    print("⚠️  WARNING: This will stop and start your Ollama service!")
    print("=" * 60)

    manager = SleepManager()

    # Check initial status
    print("\n1. Checking initial Ollama status...")
    status = manager.get_status()
    print(f"   Ollama running: {status['ollama_running']}")

    if not status['ollama_running']:
        print("   Starting Ollama first...")
        if not manager.wake_from_deep_sleep():
            print("❌ Could not start Ollama. Test aborted.")
            return False

    # Test deep sleep
    print("\n2. Testing deep sleep (stopping Ollama)...")
    if manager.enter_deep_sleep():
        print("   ✅ Deep sleep successful")
    else:
        print("   ❌ Deep sleep failed")
        return False

    time.sleep(2)

    # Verify Ollama is stopped
    print("\n3. Verifying Ollama is stopped...")
    if not manager.is_running():
        print("   ✅ Ollama confirmed stopped")
    else:
        print("   ❌ Ollama still running!")
        return False

    # Test wake from deep sleep
    print("\n4. Testing wake from deep sleep (starting Ollama)...")
    if manager.wake_from_deep_sleep():
        print("   ✅ Wake from deep sleep successful")
    else:
        print("   ❌ Wake from deep sleep failed")
        return False

    # Verify Ollama is running
    print("\n5. Verifying Ollama is running...")
    if manager.is_running():
        print("   ✅ Ollama confirmed running")
    else:
        print("   ❌ Ollama not running!")
        return False

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    return True

if __name__ == "__main__":
    import sys

    print("Sleep Manager Test")
    print("This will temporarily stop and restart Ollama service.")
    response = input("Continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        success = test_sleep_manager()
        sys.exit(0 if success else 1)
    else:
        print("Test cancelled.")
        sys.exit(0)
