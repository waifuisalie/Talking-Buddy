"""
GPIO Controller for LED Visual Feedback
Raspberry Pi 5 compatible LED control with pattern support
"""

from gpiozero import PWMLED
import threading
import time
from typing import Optional, Dict
from enum import Enum

class LEDPattern(Enum):
    """LED display patterns"""
    OFF = "off"
    SOLID = "solid"
    PULSE = "pulse"      # Breathing effect (2s cycle)
    DIM = "dim"          # 30% brightness

class LEDController:
    """
    Controls individual LEDs for chatbot state visualization
    Uses gpiozero library for clean API and built-in PWM support
    """

    def __init__(self,
                 red_pin: int = 17,
                 green_pin: int = 27,
                 blue_pin: int = 22,
                 yellow_pin: Optional[int] = 23):
        """Initialize GPIO pins for LEDs (BCM numbering)"""
        # Use PWMLED for brightness/pattern control
        self.leds: Dict[str, PWMLED] = {
            'red': PWMLED(red_pin),
            'green': PWMLED(green_pin),
            'blue': PWMLED(blue_pin),
        }

        if yellow_pin:
            self.leds['yellow'] = PWMLED(yellow_pin)

        # Pattern control
        self._pattern_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

        # Turn off all LEDs on init
        self.all_off()
        print(f"✅ LED controller initialized (pins: R{red_pin} G{green_pin} B{blue_pin}" +
              (f" Y{yellow_pin})" if yellow_pin else ")"))

    def set_state(self, state: str):
        """Set LED pattern based on chatbot state"""
        self.all_off()  # Clear previous pattern

        if state == "idle":
            self._set_white_dim()
        elif state == "listening":
            self._set_pattern('blue', LEDPattern.PULSE)
        elif state == "processing":
            if 'yellow' in self.leds:
                self._set_pattern('yellow', LEDPattern.SOLID)
            else:
                # Simulate yellow with red+green
                self._set_pattern('red', LEDPattern.SOLID)
                self._set_pattern('green', LEDPattern.SOLID)
        elif state == "speaking":
            self._set_pattern('green', LEDPattern.PULSE)
        elif state == "light_sleep":
            self._set_pattern('blue', LEDPattern.DIM)
        elif state == "deep_sleep":
            self._set_pattern('red', LEDPattern.SOLID)

    def _set_pattern(self, color: str, pattern: LEDPattern):
        """Set pattern for specific LED"""
        if color not in self.leds:
            return

        led = self.leds[color]

        if pattern == LEDPattern.OFF:
            led.off()
        elif pattern == LEDPattern.SOLID:
            led.on()
        elif pattern == LEDPattern.DIM:
            led.value = 0.3  # 30% brightness
        elif pattern == LEDPattern.PULSE:
            self._start_pulse_thread(color)

    def _start_pulse_thread(self, color: str):
        """Start breathing/pulsing effect thread"""
        self._stop_pattern_thread(color)

        stop_event = threading.Event()
        self._stop_events[color] = stop_event

        thread = threading.Thread(
            target=self._pulse_worker,
            args=(color, stop_event),
            daemon=True
        )
        self._pattern_threads[color] = thread
        thread.start()

    def _pulse_worker(self, color: str, stop_event: threading.Event):
        """Breathing effect worker - smooth fade in/out"""
        led = self.leds[color]
        while not stop_event.is_set():
            # Fade in (1 second)
            for i in range(0, 100, 2):
                if stop_event.is_set():
                    break
                led.value = i / 100.0
                time.sleep(0.02)

            # Fade out (1 second)
            for i in range(100, 0, -2):
                if stop_event.is_set():
                    break
                led.value = i / 100.0
                time.sleep(0.02)

    def _stop_pattern_thread(self, color: str):
        """Stop pattern thread for specific LED"""
        if color in self._stop_events:
            self._stop_events[color].set()

        if color in self._pattern_threads:
            thread = self._pattern_threads[color]
            if thread.is_alive():
                thread.join(timeout=1.0)
            del self._pattern_threads[color]

    def _set_white_dim(self):
        """Simulate white LED using RGB at low brightness"""
        for color in ['red', 'green', 'blue']:
            if color in self.leds:
                self.leds[color].value = 0.2  # 20% brightness

    def all_off(self):
        """Turn off all LEDs and stop all patterns"""
        with self._lock:
            # Stop all pattern threads
            for color in list(self._pattern_threads.keys()):
                self._stop_pattern_thread(color)

            # Turn off all LEDs
            for led in self.leds.values():
                led.off()

    def cleanup(self):
        """Clean up GPIO resources"""
        self.all_off()
        for led in self.leds.values():
            led.close()
        print("🧹 LED controller cleaned up")
