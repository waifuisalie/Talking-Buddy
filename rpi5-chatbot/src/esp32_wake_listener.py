"""
ESP32 Wake Listener - Listens for wake word signals from ESP32

Monitors serial port for wake word detection signals from ESP32-S3.
In testing mode, provides keyboard simulation for testing without hardware.
"""

import serial
import threading
import time
from typing import Optional, Callable
from enum import Enum

class WakeListenerMode(Enum):
    """Operating modes for wake listener"""
    SERIAL = "serial"      # Real ESP32 via serial port
    KEYBOARD = "keyboard"  # Keyboard simulation for testing
    DISABLED = "disabled"  # No wake word (always active)

class ESP32WakeListener:
    """Listens for wake word signals from ESP32-S3"""

    def __init__(
        self,
        serial_port: str = "/dev/ttyACM0",
        baud_rate: int = 115200,
        mode: WakeListenerMode = WakeListenerMode.KEYBOARD
    ):
        """
        Initialize ESP32 wake listener

        Args:
            serial_port: Serial port path (e.g., /dev/ttyACM0)
            baud_rate: Serial baud rate (default: 115200)
            mode: Operating mode (SERIAL, KEYBOARD, or DISABLED)
        """
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.mode = mode

        # Serial connection
        self._serial: Optional[serial.Serial] = None
        self._is_running = False
        self._listen_thread: Optional[threading.Thread] = None

        # Callbacks
        self._wake_callback: Optional[Callable] = None

        # Statistics
        self.wake_count = 0
        self.last_wake_time: Optional[float] = None

    def register_wake_callback(self, callback: Callable):
        """
        Register callback for wake word detection

        Args:
            callback: Function to call when wake word detected
        """
        self._wake_callback = callback

    def start(self) -> bool:
        """
        Start listening for wake word

        Returns:
            True if started successfully, False otherwise
        """
        if self._is_running:
            print("⚠️  ESP32 wake listener already running")
            return True

        if self.mode == WakeListenerMode.DISABLED:
            print("ℹ️  Wake word detection disabled")
            return True

        if self.mode == WakeListenerMode.KEYBOARD:
            print("⌨️  Wake word listener in KEYBOARD mode")
            print("   Press 'w' + Enter to simulate wake word")
            self._is_running = True
            self._listen_thread = threading.Thread(
                target=self._keyboard_listener,
                daemon=True,
                name="KeyboardWakeListener"
            )
            self._listen_thread.start()
            return True

        if self.mode == WakeListenerMode.SERIAL:
            return self._start_serial()

        return False

    def _start_serial(self) -> bool:
        """Start serial port listening"""
        try:
            print(f"📡 Connecting to ESP32 on {self.serial_port}...")

            self._serial = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=1
            )

            self._is_running = True
            self._listen_thread = threading.Thread(
                target=self._serial_listener,
                daemon=True,
                name="ESP32WakeListener"
            )
            self._listen_thread.start()

            print(f"✅ ESP32 wake listener started on {self.serial_port}")
            return True

        except serial.SerialException as e:
            print(f"❌ Failed to open serial port {self.serial_port}: {e}")
            return False
        except Exception as e:
            print(f"❌ Error starting ESP32 listener: {e}")
            return False

    def stop(self):
        """Stop listening for wake word"""
        if not self._is_running:
            return

        print("🛑 Stopping ESP32 wake listener...")
        self._is_running = False

        # Wait for thread to finish
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)

        # Close serial port
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None

        print("✅ ESP32 wake listener stopped")

    def _serial_listener(self):
        """Serial port listener thread"""
        print("👂 Listening for ESP32 wake word signals...")

        while self._is_running:
            try:
                if self._serial and self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8', errors='ignore').strip()

                    if line:
                        # Check for wake word signal
                        if "WAKE_WORD_DETECTED" in line:
                            print("🎙️  Wake word detected by ESP32!")
                            self._trigger_wake()

                            # Optional: Send acknowledgment back to ESP32
                            if self._serial:
                                self._serial.write(b"ACK_WAKE\n")
                        else:
                            # Log other serial output for debugging
                            print(f"[ESP32] {line}")

                time.sleep(0.01)  # Small delay to avoid busy-waiting

            except serial.SerialException as e:
                print(f"❌ Serial error: {e}")
                break
            except Exception as e:
                print(f"❌ Error in serial listener: {e}")
                time.sleep(1)

    def _keyboard_listener(self):
        """Keyboard input listener thread (for testing)"""
        print("👂 Keyboard wake listener ready...")

        while self._is_running:
            try:
                user_input = input()

                if user_input.strip().lower() == 'w':
                    print("⌨️  Simulated wake word detected!")
                    self._trigger_wake()

            except EOFError:
                # Input stream closed
                break
            except Exception as e:
                print(f"❌ Error in keyboard listener: {e}")
                time.sleep(1)

    def _trigger_wake(self):
        """Trigger wake callback"""
        self.wake_count += 1
        self.last_wake_time = time.time()

        if self._wake_callback:
            try:
                self._wake_callback()
            except Exception as e:
                print(f"❌ Error in wake callback: {e}")

    def send_sleep_signal(self):
        """
        Send sleep signal to ESP32 (optional)

        Tells ESP32 that Raspberry Pi is going to sleep
        """
        if self.mode == WakeListenerMode.SERIAL and self._serial and self._serial.is_open:
            try:
                self._serial.write(b"CHATBOT_SLEEPING\n")
                print("📤 Sent sleep signal to ESP32")
            except Exception as e:
                print(f"❌ Error sending sleep signal: {e}")

    def is_running(self) -> bool:
        """Check if listener is running"""
        return self._is_running

    def get_stats(self) -> dict:
        """Get listener statistics"""
        return {
            "mode": self.mode.value,
            "is_running": self._is_running,
            "wake_count": self.wake_count,
            "last_wake_time": self.last_wake_time,
            "serial_port": self.serial_port if self.mode == WakeListenerMode.SERIAL else None
        }

def test_wake_listener():
    """Test the wake listener in keyboard mode"""
    print("Testing ESP32 Wake Listener:")
    print("=" * 60)

    listener = ESP32WakeListener(mode=WakeListenerMode.KEYBOARD)

    wake_triggered = False

    def on_wake():
        nonlocal wake_triggered
        wake_triggered = True
        print("✅ Wake callback triggered!")

    listener.register_wake_callback(on_wake)

    print("\nStarting listener...")
    if listener.start():
        print("✅ Listener started")
    else:
        print("❌ Failed to start listener")
        return False

    print("\nPress 'w' + Enter to test wake word (or Ctrl+C to quit)")
    print("Waiting for wake word...")

    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopping listener...")
        listener.stop()

        stats = listener.get_stats()
        print(f"\nStatistics:")
        print(f"  Wake count: {stats['wake_count']}")
        print(f"  Mode: {stats['mode']}")

        if stats['wake_count'] > 0:
            print("\n✅ Test successful!")
            return True
        else:
            print("\n⚠️  No wake words detected")
            return False

if __name__ == "__main__":
    test_wake_listener()
