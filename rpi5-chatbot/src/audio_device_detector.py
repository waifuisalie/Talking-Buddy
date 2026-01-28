"""
Audio Device Detection and Auto-Configuration

Intelligently detects and selects audio input/output devices for TalkingBuddy.
Supports multiple hardware configurations:
- P2 (3.5mm jack) + USB microphone
- HiFiBerry DAC + USB microphone
- USB audio output + USB microphone

Architecture:
- Uses PyAudio to enumerate available devices
- Applies intelligent scoring algorithm to prioritize devices
- Extracts stable ALSA device names for configuration
- Provides validation and troubleshooting feedback
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional, List
from contextlib import redirect_stderr

try:
    import pyaudio
except ImportError:
    print("⚠️  PyAudio not installed. Run: pip install pyaudio")
    pyaudio = None


@dataclass
class AudioDeviceInfo:
    """Information about an audio device"""
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    alsa_name: Optional[str]  # Extracted ALSA device name
    score: int  # Priority score for auto-selection


class AudioDeviceDetector:
    """Intelligent audio device detection and selection"""

    def __init__(self, debug_mode: bool = False):
        """
        Initialize audio device detector

        Args:
            debug_mode: Enable debug output
        """
        self.debug_mode = debug_mode
        self.audio = None
        self.devices: List[AudioDeviceInfo] = []

    def initialize(self) -> bool:
        """
        Initialize PyAudio with ALSA warnings suppressed

        Returns:
            True if initialization succeeded, False otherwise
        """
        if not pyaudio:
            print("❌ PyAudio not available")
            return False

        try:
            # Suppress ALSA warnings (cosmetic only)
            with open(os.devnull, 'w') as devnull:
                with redirect_stderr(devnull):
                    self.audio = pyaudio.PyAudio()

            if self.debug_mode:
                print("✅ PyAudio initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to initialize PyAudio: {e}")
            return False

    def list_all_devices(self) -> List[AudioDeviceInfo]:
        """
        Enumerate all available audio devices

        Returns:
            List of AudioDeviceInfo objects
        """
        if not self.audio:
            return []

        self.devices = []

        try:
            device_count = self.audio.get_device_count()

            for i in range(device_count):
                try:
                    info = self.audio.get_device_info_by_index(i)

                    device = AudioDeviceInfo(
                        index=i,
                        name=info['name'],
                        max_input_channels=info['maxInputChannels'],
                        max_output_channels=info['maxOutputChannels'],
                        default_sample_rate=info['defaultSampleRate'],
                        alsa_name=None,  # Will be extracted if needed
                        score=0  # Will be calculated during detection
                    )

                    self.devices.append(device)

                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️  Failed to get info for device {i}: {e}")

            if self.debug_mode:
                print(f"📋 Found {len(self.devices)} audio devices")

            return self.devices

        except Exception as e:
            print(f"❌ Error listing devices: {e}")
            return []

    def detect_input_device(
        self,
        user_preference: Optional[str] = None,
        config_preference: Optional[str] = None
    ) -> Optional[AudioDeviceInfo]:
        """
        Detect best input device using scoring algorithm

        Args:
            user_preference: User override from CLI (pattern or index)
            config_preference: Config file device name

        Returns:
            Best AudioDeviceInfo for input, or None if not found
        """
        # Ensure devices are listed
        if not self.devices:
            self.list_all_devices()

        # Filter to input devices only
        input_devices = [d for d in self.devices if d.max_input_channels > 0]

        if not input_devices:
            print("❌ No input devices found")
            return None

        # Handle user CLI override
        if user_preference:
            device = self._find_device_by_preference(input_devices, user_preference, is_input=True)
            if device:
                device.score = 1000
                device.alsa_name = self._extract_alsa_name(device, is_input=True)
                return device
            else:
                print(f"⚠️  User-specified input device '{user_preference}' not found")

        # Handle config file preference
        if config_preference:
            device = self._find_device_by_preference(input_devices, config_preference, is_input=True)
            if device:
                device.score = 900
                device.alsa_name = self._extract_alsa_name(device, is_input=True)
                if self.debug_mode:
                    print(f"✅ Using config input device: {device.name}")
                return device

        # Auto-detect using scoring
        for device in input_devices:
            device.score = self._score_input_device(device)
            device.alsa_name = self._extract_alsa_name(device, is_input=True)

        # Sort by score (highest first)
        input_devices.sort(key=lambda d: d.score, reverse=True)

        best_device = input_devices[0]

        if self.debug_mode:
            print(f"🎤 Auto-detected input: {best_device.name} (score: {best_device.score})")

        return best_device

    def detect_output_device(
        self,
        user_preference: Optional[str] = None,
        config_preference: Optional[str] = None
    ) -> Optional[AudioDeviceInfo]:
        """
        Detect best output device using scoring algorithm

        Args:
            user_preference: User override from CLI (pattern or index)
            config_preference: Config file device name

        Returns:
            Best AudioDeviceInfo for output, or None if not found
        """
        # Ensure devices are listed
        if not self.devices:
            self.list_all_devices()

        # Filter to output devices only
        output_devices = [d for d in self.devices if d.max_output_channels > 0]

        if not output_devices:
            print("❌ No output devices found")
            return None

        # Handle user CLI override
        if user_preference:
            device = self._find_device_by_preference(output_devices, user_preference, is_input=False)
            if device:
                device.score = 1000
                device.alsa_name = self._extract_alsa_name(device, is_input=False)
                return device
            else:
                print(f"⚠️  User-specified output device '{user_preference}' not found")

        # Handle config file preference
        if config_preference:
            device = self._find_device_by_preference(output_devices, config_preference, is_input=False)
            if device:
                device.score = 900
                device.alsa_name = self._extract_alsa_name(device, is_input=False)
                if self.debug_mode:
                    print(f"✅ Using config output device: {device.name}")
                return device

        # Auto-detect using scoring
        for device in output_devices:
            device.score = self._score_output_device(device)
            device.alsa_name = self._extract_alsa_name(device, is_input=False)

        # Sort by score (highest first)
        output_devices.sort(key=lambda d: d.score, reverse=True)

        best_device = output_devices[0]

        if self.debug_mode:
            print(f"🔊 Auto-detected output: {best_device.name} (score: {best_device.score})")

        return best_device

    def _find_device_by_preference(
        self,
        devices: List[AudioDeviceInfo],
        preference: str,
        is_input: bool
    ) -> Optional[AudioDeviceInfo]:
        """
        Find device matching user preference (pattern or index)

        Args:
            devices: List of devices to search
            preference: Pattern or index string
            is_input: True for input devices, False for output

        Returns:
            Matching device or None
        """
        # Try as index first
        try:
            index = int(preference)
            for device in devices:
                if device.index == index:
                    return device
        except ValueError:
            pass

        # Try as pattern (case-insensitive substring match)
        preference_lower = preference.lower()
        for device in devices:
            if preference_lower in device.name.lower():
                return device

        return None

    def _score_input_device(self, device: AudioDeviceInfo) -> int:
        """
        Calculate priority score for input device

        Scoring (highest to lowest):
        - USB microphones: 700-800
        - Built-in microphone: 500
        - PulseAudio virtual devices: 50 (deprioritized)
        - System default: 100

        Args:
            device: Device to score

        Returns:
            Priority score
        """
        name_lower = device.name.lower()

        # Deprioritize PulseAudio virtual devices
        if self._is_pulseaudio_device(device):
            return 50

        # USB microphones (high priority)
        if 'usb' in name_lower:
            # Higher score for dedicated audio devices
            if 'audio' in name_lower or 'microphone' in name_lower or 'mic' in name_lower:
                return 800
            return 700

        # Built-in microphone
        if 'bcm2835' in name_lower or 'builtin' in name_lower or 'internal' in name_lower:
            return 500

        # System default
        return 100

    def _score_output_device(self, device: AudioDeviceInfo) -> int:
        """
        Calculate priority score for output device

        Scoring (highest to lowest):
        - HiFiBerry DAC: 850
        - USB speakers/DAC: 700
        - 3.5mm headphone jack: 600
        - HDMI audio: 500
        - PulseAudio virtual devices: 50 (deprioritized)
        - System default: 100

        Args:
            device: Device to score

        Returns:
            Priority score
        """
        name_lower = device.name.lower()

        # Deprioritize PulseAudio virtual devices
        if self._is_pulseaudio_device(device):
            return 50

        # HiFiBerry DAC (highest priority)
        if 'hifiberry' in name_lower or 'sndrpihifiberry' in name_lower:
            return 850

        # USB audio output
        if 'usb' in name_lower:
            return 700

        # 3.5mm headphone jack (P2)
        if 'headphones' in name_lower or 'bcm2835' in name_lower:
            return 600

        # HDMI audio
        if 'hdmi' in name_lower or 'vc4-hdmi' in name_lower:
            return 500

        # System default
        return 100

    def _is_pulseaudio_device(self, device: AudioDeviceInfo) -> bool:
        """
        Detect if device is a PulseAudio virtual device

        Args:
            device: Device to check

        Returns:
            True if PulseAudio device, False otherwise
        """
        return 'pulse' in device.name.lower()

    def _extract_alsa_name(self, device: AudioDeviceInfo, is_input: bool) -> Optional[str]:
        """
        Extract ALSA device name from PyAudio device info

        Args:
            device: Device to extract ALSA name from
            is_input: True for input (use plughw), False for output (use hw)

        Returns:
            ALSA device name (e.g., "plughw:CARD=Device,DEV=0") or None
        """
        # Skip ALSA extraction for PulseAudio devices
        if self._is_pulseaudio_device(device):
            return None

        try:
            # Try to extract from device name
            # Common patterns: "hw:3,0", "plughw:CARD=Device,DEV=0"
            import re

            # Pattern 1: Extract card name from device name
            # Example: "USB PnP Sound Device: Audio (hw:3,0)"
            hw_pattern = r'hw:(\d+),(\d+)'
            match = re.search(hw_pattern, device.name)

            if match:
                card_num = match.group(1)
                dev_num = match.group(2)

                # For input, use plughw (plug layer for format conversion)
                # For output, use hw (direct hardware access)
                prefix = "plughw" if is_input else "hw"

                # Try to extract card name if available
                # Pattern: "CardName: ..." or just use the number
                return f"{prefix}:CARD={card_num},DEV={dev_num}"

            # If extraction failed, return None (will use PyAudio index fallback)
            return None

        except Exception as e:
            if self.debug_mode:
                print(f"⚠️  Failed to extract ALSA name for {device.name}: {e}")
            return None

    def validate_device(self, device: AudioDeviceInfo, is_input: bool) -> bool:
        """
        Validate that a device can be opened

        Args:
            device: Device to validate
            is_input: True for input, False for output

        Returns:
            True if device can be opened, False otherwise
        """
        if not self.audio:
            return False

        try:
            # Try to open the device
            stream_kwargs = {
                'format': pyaudio.paInt16,
                'channels': 1,
                'rate': int(device.default_sample_rate),
                'input': is_input,
                'output': not is_input,
                'input_device_index': device.index if is_input else None,
                'output_device_index': device.index if not is_input else None,
                'frames_per_buffer': 1024
            }

            # Remove None values
            stream_kwargs = {k: v for k, v in stream_kwargs.items() if v is not None}

            # Suppress ALSA warnings during validation
            with open(os.devnull, 'w') as devnull:
                with redirect_stderr(devnull):
                    stream = self.audio.open(**stream_kwargs)
                    stream.close()

            return True

        except Exception as e:
            if self.debug_mode:
                print(f"⚠️  Device validation failed for {device.name}: {e}")
            return False

    def cleanup(self):
        """Terminate PyAudio resources"""
        if self.audio:
            self.audio.terminate()
            self.audio = None
            if self.debug_mode:
                print("✅ PyAudio cleaned up")


def print_device_troubleshooting(is_input: bool):
    """
    Print troubleshooting information for device detection failures

    Args:
        is_input: True for input devices, False for output
    """
    device_type = "input" if is_input else "output"
    device_name = "microphone" if is_input else "speaker/output"

    print(f"\n❌ Audio Device Error: No {device_type} devices detected")
    print("\nPossible causes:")
    print(f"  • No {device_name} connected")
    if is_input:
        print("  • USB microphone not recognized by system")
    print("  • Permissions issue (check audio group membership)")
    print("\nTroubleshooting:")
    print("  1. List available devices: python src/run_chatbot.py --list-devices")

    if is_input:
        print("  2. Check system devices: arecord -l")
    else:
        print("  2. Check system devices: aplay -l")

    print("  3. Verify USB connection: lsusb")
    print("  4. Check permissions: groups (should include 'audio')")

    if is_input:
        print("\n💡 Tip: USB microphones usually appear as 'USB Audio Device' or 'USB PnP Sound'")
    else:
        print("\n💡 Tip: Use --output-device to manually specify output device")


if __name__ == "__main__":
    """Test audio device detection"""
    print("🎤 Audio Device Detector - Test Mode")
    print("=" * 60)

    detector = AudioDeviceDetector(debug_mode=True)

    if not detector.initialize():
        print("❌ Failed to initialize detector")
        sys.exit(1)

    devices = detector.list_all_devices()

    print(f"\n📋 Found {len(devices)} devices total")

    # List input devices
    print("\n" + "=" * 60)
    print("INPUT DEVICES (Microphones)")
    print("=" * 60)

    input_devices = [d for d in devices if d.max_input_channels > 0]
    for device in input_devices:
        print(f"\n  [{device.index}] {device.name}")
        print(f"      Channels: {device.max_input_channels} input")
        print(f"      Sample Rate: {device.default_sample_rate} Hz")
        alsa_name = detector._extract_alsa_name(device, is_input=True)
        if alsa_name:
            print(f"      ALSA: {alsa_name}")

    # List output devices
    print("\n" + "=" * 60)
    print("OUTPUT DEVICES (Speakers)")
    print("=" * 60)

    output_devices = [d for d in devices if d.max_output_channels > 0]
    for device in output_devices:
        print(f"\n  [{device.index}] {device.name}")
        print(f"      Channels: {device.max_output_channels} output")
        print(f"      Sample Rate: {device.default_sample_rate} Hz")
        alsa_name = detector._extract_alsa_name(device, is_input=False)
        if alsa_name:
            print(f"      ALSA: {alsa_name}")

    # Test auto-detection
    print("\n" + "=" * 60)
    print("AUTO-DETECTION TEST")
    print("=" * 60)

    best_input = detector.detect_input_device()
    if best_input:
        print(f"\n✅ Best input: {best_input.name}")
        print(f"   Score: {best_input.score}")
        if best_input.alsa_name:
            print(f"   ALSA: {best_input.alsa_name}")
    else:
        print("\n❌ No input device detected")

    best_output = detector.detect_output_device()
    if best_output:
        print(f"\n✅ Best output: {best_output.name}")
        print(f"   Score: {best_output.score}")
        if best_output.alsa_name:
            print(f"   ALSA: {best_output.alsa_name}")
    else:
        print("\n❌ No output device detected")

    detector.cleanup()
    print("\n✅ Test complete!")
