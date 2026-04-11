"""
Battery monitor for DFRobot FIT0992 UPS HAT (MAX17040 fuel gauge).
Reads voltage, SOC%, and AC power status via I2C + GPIO.
"""

import threading
import time


class BatteryMonitor:
    I2C_BUS = 1
    I2C_ADDR = 0x36
    GPIO_CHIP = '/dev/gpiochip4'
    GPIO_AC_LINE = 6
    CACHE_TTL = 2  # seconds

    def __init__(self):
        import smbus2
        import gpiod

        self._lock = threading.Lock()
        self._cache = None
        self._cache_time = 0

        # I2C
        self._bus = smbus2.SMBus(self.I2C_BUS)

        # Verify chip is present
        self._bus.read_word_data(self.I2C_ADDR, 0x08)

        # GPIO for AC power detection
        self._gpio_req = None
        try:
            chip = gpiod.Chip(self.GPIO_CHIP)
            line_config = gpiod.LineSettings(direction=gpiod.line.Direction.INPUT)
            self._gpio_req = chip.request_lines(
                config={self.GPIO_AC_LINE: line_config},
                consumer='talkingbuddy-battery'
            )
        except OSError:
            # GPIO line busy or unavailable — charging detection disabled
            pass

    def read(self):
        now = time.monotonic()
        if self._cache and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        try:
            with self._lock:
                # Voltage (register 0x02)
                raw_v = self._bus.read_word_data(self.I2C_ADDR, 0x02)
                raw_v = ((raw_v & 0xFF) << 8) | (raw_v >> 8)
                voltage = round(raw_v * 1.25 / 1000 / 16, 3)

                # SOC (register 0x04)
                raw_s = self._bus.read_word_data(self.I2C_ADDR, 0x04)
                raw_s = ((raw_s & 0xFF) << 8) | (raw_s >> 8)
                soc = max(0.0, min(100.0, raw_s / 256.0))

                # AC power status
                charging = None
                if self._gpio_req:
                    import gpiod
                    val = self._gpio_req.get_value(self.GPIO_AC_LINE)
                    charging = val == gpiod.line.Value.ACTIVE

            result = {
                'available': True,
                'voltage': voltage,
                'soc': round(soc, 1),
                'charging': charging,
            }
            self._cache = result
            self._cache_time = now
            return result

        except (OSError, IOError):
            if self._cache:
                return self._cache
            return {'available': False}

    def close(self):
        try:
            self._bus.close()
        except Exception:
            pass
        if self._gpio_req:
            try:
                self._gpio_req.release()
            except Exception:
                pass
