"""
Timeout Manager - Manages conversation and idle timeouts

Handles two types of timeouts:
1. Conversation timeout (30 seconds) - Auto-sleep after user stops talking
2. Idle timeout (5 minutes) - Transition to deep sleep after extended idle
"""

import time
import threading
from typing import Callable, Optional
from enum import Enum

class TimeoutType(Enum):
    """Types of timeouts"""
    CONVERSATION = "conversation"  # 30 seconds of silence
    IDLE = "idle"                  # 5 minutes in light sleep

class TimeoutManager:
    """Manages timeouts for conversation and idle states"""

    def __init__(
        self,
        conversation_timeout: float = 30.0,  # 30 seconds
        idle_timeout: float = 300.0           # 5 minutes
    ):
        """
        Initialize timeout manager

        Args:
            conversation_timeout: Seconds of silence before auto-sleep (default: 30s)
            idle_timeout: Seconds in light sleep before deep sleep (default: 5min)
        """
        self.conversation_timeout = conversation_timeout
        self.idle_timeout = idle_timeout

        # Timer state
        self._conversation_timer: Optional[threading.Timer] = None
        self._idle_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # Callbacks
        self._conversation_callback: Optional[Callable] = None
        self._idle_callback: Optional[Callable] = None

        # Monitoring flags
        self._is_monitoring = False

    def register_conversation_callback(self, callback: Callable):
        """
        Register callback for conversation timeout

        Args:
            callback: Function to call when conversation times out
        """
        self._conversation_callback = callback

    def register_idle_callback(self, callback: Callable):
        """
        Register callback for idle timeout

        Args:
            callback: Function to call when idle times out
        """
        self._idle_callback = callback

    def start_conversation_timer(self):
        """
        Start the conversation timeout timer

        Resets any existing conversation timer. Call this after each
        time the AI finishes speaking.
        """
        with self._lock:
            # Cancel existing timer
            if self._conversation_timer:
                self._conversation_timer.cancel()

            # Start new timer
            self._conversation_timer = threading.Timer(
                self.conversation_timeout,
                self._on_conversation_timeout
            )
            self._conversation_timer.daemon = True
            self._conversation_timer.start()

            print(f"⏰ Conversation timer started ({self.conversation_timeout}s)")

    def reset_conversation_timer(self):
        """
        Reset the conversation timer (user is speaking/active)

        Call this when user provides input to prevent timeout.
        """
        with self._lock:
            if self._conversation_timer:
                self._conversation_timer.cancel()
                self._conversation_timer = None
                print("🔄 Conversation timer reset")

    def stop_conversation_timer(self):
        """Stop the conversation timer"""
        with self._lock:
            if self._conversation_timer:
                self._conversation_timer.cancel()
                self._conversation_timer = None
                print("🛑 Conversation timer stopped")

    def start_idle_timer(self):
        """
        Start the idle timeout timer

        Call this when entering light sleep mode.
        """
        with self._lock:
            # Cancel existing timer
            if self._idle_timer:
                self._idle_timer.cancel()

            # Start new timer
            self._idle_timer = threading.Timer(
                self.idle_timeout,
                self._on_idle_timeout
            )
            self._idle_timer.daemon = True
            self._idle_timer.start()

            print(f"⏰ Idle timer started ({self.idle_timeout/60:.1f} minutes)")

    def reset_idle_timer(self):
        """
        Reset the idle timer (wake word detected)

        Call this when waking from light sleep to restart idle countdown.
        """
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
                print("🔄 Idle timer reset")

    def stop_idle_timer(self):
        """Stop the idle timer"""
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
                print("🛑 Idle timer stopped")

    def stop_all_timers(self):
        """Stop all active timers"""
        self.stop_conversation_timer()
        self.stop_idle_timer()

    def is_conversation_timer_active(self) -> bool:
        """Check if conversation timer is running"""
        with self._lock:
            return self._conversation_timer is not None and self._conversation_timer.is_alive()

    def is_idle_timer_active(self) -> bool:
        """Check if idle timer is running"""
        with self._lock:
            return self._idle_timer is not None and self._idle_timer.is_alive()

    def _on_conversation_timeout(self):
        """Internal callback when conversation times out"""
        print("⏰ Conversation timeout reached (30s silence)")

        if self._conversation_callback:
            try:
                self._conversation_callback()
            except Exception as e:
                print(f"❌ Error in conversation timeout callback: {e}")

    def _on_idle_timeout(self):
        """Internal callback when idle times out"""
        print("⏰ Idle timeout reached (5 min in light sleep)")

        if self._idle_callback:
            try:
                self._idle_callback()
            except Exception as e:
                print(f"❌ Error in idle timeout callback: {e}")

    def get_status(self) -> dict:
        """Get current timer status"""
        return {
            "conversation_timer_active": self.is_conversation_timer_active(),
            "idle_timer_active": self.is_idle_timer_active(),
            "conversation_timeout": self.conversation_timeout,
            "idle_timeout": self.idle_timeout
        }

def test_timeout_manager():
    """Test the timeout manager"""
    print("Testing Timeout Manager:")
    print("=" * 60)

    # Test with short timeouts
    manager = TimeoutManager(
        conversation_timeout=2.0,  # 2 seconds for testing
        idle_timeout=5.0           # 5 seconds for testing
    )

    # Register callbacks
    conversation_triggered = False
    idle_triggered = False

    def on_conversation_timeout():
        nonlocal conversation_triggered
        conversation_triggered = True
        print("✅ Conversation timeout callback triggered")

    def on_idle_timeout():
        nonlocal idle_triggered
        idle_triggered = True
        print("✅ Idle timeout callback triggered")

    manager.register_conversation_callback(on_conversation_timeout)
    manager.register_idle_callback(on_idle_timeout)

    # Test 1: Conversation timeout
    print("\nTest 1: Conversation timeout (2s)")
    manager.start_conversation_timer()
    time.sleep(2.5)
    assert conversation_triggered, "Conversation timeout should have triggered"

    # Test 2: Idle timeout
    print("\nTest 2: Idle timeout (5s)")
    manager.start_idle_timer()
    time.sleep(5.5)
    assert idle_triggered, "Idle timeout should have triggered"

    # Test 3: Reset before timeout
    print("\nTest 3: Reset conversation timer before timeout")
    conversation_triggered = False
    manager.start_conversation_timer()
    time.sleep(1.0)
    manager.reset_conversation_timer()
    time.sleep(1.5)
    assert not conversation_triggered, "Conversation timeout should NOT have triggered after reset"

    # Test 4: Stop timer
    print("\nTest 4: Stop timer before timeout")
    idle_triggered = False
    manager.start_idle_timer()
    time.sleep(2.0)
    manager.stop_idle_timer()
    time.sleep(4.0)
    assert not idle_triggered, "Idle timeout should NOT have triggered after stop"

    print("\n" + "=" * 60)
    print("All tests passed!")

if __name__ == "__main__":
    test_timeout_manager()
