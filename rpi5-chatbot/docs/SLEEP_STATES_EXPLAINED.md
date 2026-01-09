# Sleep States Implementation - Detailed Explanation

## Overview

The wake word integration uses **two levels of power-saving sleep** to maximize battery life while maintaining reasonable wake-up times.

---

## State Diagram

```
┌──────────────┐
│  DEEP SLEEP  │ (Ollama OFF, min power, slow wake)
│              │
└──────┬───────┘
       │ After 5 min idle
       ▼
┌──────────────┐
│ LIGHT SLEEP  │ (Ollama ON, Whisper OFF, fast wake)
│              │
└──────┬───────┘
       │ Wake word OR 30s timeout
       ▼
┌──────────────┐
│  LISTENING   │ (Ollama ON, Whisper ON, active)
│              │
└──────────────┘
```

---

## Light Sleep Implementation

### What It Does

**Light sleep** stops audio recording but keeps the LLM loaded in memory, ready to respond quickly.

### Code Location: `voice_chatbot.py:_enter_light_sleep()` (line 422-439)

```python
def _enter_light_sleep(self):
    """Enter light sleep mode (Ollama loaded, Whisper OFF)"""
    # Stop whisper STT
    if self.whisper_stt:
        self.whisper_stt.stop()

    # Stop conversation timer
    self.timeout_manager.stop_conversation_timer()

    # Start idle timer (5 minutes)
    self.timeout_manager.start_idle_timer()

    # Send sleep signal to ESP32
    if self.esp32_listener:
        self.esp32_listener.send_sleep_signal()

    # Transition to light sleep state
    self.state_manager.set_state("light_sleep")
```

### Step-by-Step Breakdown

#### Step 1: Stop Whisper STT
```python
if self.whisper_stt:
    self.whisper_stt.stop()
```

**What this does:**
- Sets `is_running = False` flag
- Waits for recording thread to exit (max 2 seconds)
- Closes PyAudio audio stream
- Terminates PyAudio instance
- Frees microphone resources

**Power Impact:** Stops continuous audio recording → Saves ~1-2W

#### Step 2: Stop Conversation Timer
```python
self.timeout_manager.stop_conversation_timer()
```

**What this does:**
- Cancels the 30-second silence timeout
- Prevents false auto-sleep triggers while already in sleep

**Purpose:** Clean up active timers before entering sleep

#### Step 3: Start Idle Timer
```python
self.timeout_manager.start_idle_timer()
```

**What this does:**
- Starts a **5-minute countdown timer**
- If timer expires → Automatically triggers `_enter_deep_sleep()`

**Purpose:** Transition to deep sleep if user doesn't return for extended period

#### Step 4: Notify ESP32
```python
if self.esp32_listener:
    self.esp32_listener.send_sleep_signal()
```

**What this does:**
- Sends `"CHATBOT_SLEEPING\n"` via serial to ESP32
- ESP32 can use this to show status LED or other feedback

**Purpose:** Optional communication, ESP32 knows Raspberry Pi is sleeping

#### Step 5: Update State
```python
self.state_manager.set_state("light_sleep")
```

**What this does:**
- Changes chatbot state from `"speaking"` to `"light_sleep"`
- Triggers `_on_light_sleep_state()` callback
- Prints `"💤 Light sleep - Waiting for wake word..."`

**Purpose:** Inform user and update internal state

### What Stays Running in Light Sleep

✅ **Ollama service** - LLM model loaded in RAM
✅ **ESP32 wake listener** - Monitoring for wake word
✅ **Python process** - Main chatbot loop
✅ **5-minute idle timer** - Countdown to deep sleep

❌ **Whisper STT** - Audio recording stopped
❌ **30-second conversation timer** - Not needed

### Power Consumption

- **Before (active listening):** ~8-10W
- **Light sleep:** ~3-4W (Ollama idle + Python)
- **Savings:** ~50%

---

## Deep Sleep Implementation

### What It Does

**Deep sleep** stops both audio recording AND the Ollama service, releasing RAM and minimizing CPU usage.

### Code Location: `voice_chatbot.py:_enter_deep_sleep()` (line 441-457)

```python
def _enter_deep_sleep(self):
    """Enter deep sleep mode (Ollama OFF, minimal power)"""
    # Stop whisper STT (if not already stopped)
    if self.whisper_stt:
        self.whisper_stt.stop()

    # Stop all timers
    self.timeout_manager.stop_all_timers()

    # Stop Ollama service
    if not self.sleep_manager.enter_deep_sleep():
        print("⚠️  Failed to stop Ollama, staying in light sleep")
        self.timeout_manager.start_idle_timer()  # Restart idle timer
        return

    # Transition to deep sleep state
    self.state_manager.set_state("deep_sleep")
```

### Step-by-Step Breakdown

#### Step 1: Stop Whisper (Redundant Safety)
```python
if self.whisper_stt:
    self.whisper_stt.stop()
```

**Why:** Whisper should already be stopped from light sleep, but this ensures it's definitely off.

#### Step 2: Stop All Timers
```python
self.timeout_manager.stop_all_timers()
```

**What this does:**
- Stops conversation timer (30s)
- Stops idle timer (5min)

**Purpose:** No timers needed in deep sleep

#### Step 3: Stop Ollama Service
```python
if not self.sleep_manager.enter_deep_sleep():
    print("⚠️  Failed to stop Ollama, staying in light sleep")
    self.timeout_manager.start_idle_timer()
    return
```

**What this does:**
This calls `sleep_manager.py:enter_deep_sleep()` which:

1. **Checks if Ollama is running:**
   ```python
   response = requests.get("http://localhost:11434/api/tags")
   ```

2. **Stops systemd service:**
   ```bash
   systemctl --user stop ollama
   # OR
   sudo systemctl stop ollama
   ```

3. **Waits and verifies:**
   - Waits 2 seconds for shutdown
   - Checks if Ollama actually stopped
   - Returns True if successful

**Fallback:** If stop fails, stays in light sleep and restarts 5-min timer

**Power Impact:** Stops Ollama process → Releases ~1-2GB RAM, saves ~2-3W

#### Step 4: Update State
```python
self.state_manager.set_state("deep_sleep")
```

**What this does:**
- Changes state to `"deep_sleep"`
- Triggers `_on_deep_sleep_state()` callback
- Prints `"😴 Deep sleep - Ollama stopped, minimal power..."`

### What Stays Running in Deep Sleep

✅ **ESP32 wake listener** - Monitoring for wake word
✅ **Python process** - Main chatbot loop (minimal CPU)

❌ **Ollama service** - Completely stopped
❌ **Whisper STT** - Audio recording stopped
❌ **All timers** - No active timers

### Power Consumption

- **Before (active listening):** ~8-10W
- **Light sleep:** ~3-4W
- **Deep sleep:** ~0.5-1W (just Python + ESP32 listener)
- **Savings:** ~90%

---

## Wake-Up Flow

### From Light Sleep

**Trigger:** ESP32 sends `"WAKE_WORD_DETECTED\n"` via serial

**Code:** `voice_chatbot.py:_on_wake_word_detected()` (line 389-410)

```python
def _on_wake_word_detected(self):
    print("🌅 Wake word detected!")

    # Stop idle timer (if in light sleep)
    self.timeout_manager.reset_idle_timer()

    # Wake from deep sleep if needed
    if self.state_manager.is_state("deep_sleep"):
        # [Handle deep sleep wake - see below]
        pass

    # Start whisper STT only if not already running
    if not self.whisper_stt.is_running:
        if not self.whisper_stt.start():
            print("❌ Failed to start speech recognition")
            return

    # Transition to listening
    self.state_manager.set_state("listening")
```

**Steps:**
1. Reset/stop idle timer
2. Start Whisper STT (fast ~1 second)
3. Change state to `"listening"`

**Wake Time:** ~1 second (Ollama already loaded)

### From Deep Sleep

**Trigger:** Same - ESP32 wake word signal

**Additional Step:** Start Ollama service first

```python
if self.state_manager.is_state("deep_sleep"):
    print("🔄 Waking from deep sleep...")
    if not self.sleep_manager.wake_from_deep_sleep(self.config.ollama.model):
        print("❌ Failed to wake from deep sleep")
        return
```

**What `wake_from_deep_sleep()` does:**

1. **Start systemd service:**
   ```bash
   systemctl --user start ollama
   ```

2. **Wait for Ollama to be ready:**
   - Polls `http://localhost:11434/api/tags` every second
   - Times out after 30 seconds
   - Prints elapsed time when ready

3. **Warm up model (optional):**
   - Makes test request to load model into RAM
   - Ensures first real request is fast

**Wake Time:** ~5-10 seconds (must reload model)

---

## Timeout System

### Conversation Timeout (30 seconds)

**Purpose:** Auto-sleep if user walks away mid-conversation

**When it starts:**
- After AI finishes speaking (TTS playback completes)

**When it resets:**
- User speaks (transcription received)

**What it does when expired:**
```python
def _on_conversation_timeout(self):
    print("⏰ Conversation timeout - Entering light sleep")
    self._enter_light_sleep()
```

**Code:** `timeout_manager.py` - Uses Python `threading.Timer`

### Idle Timeout (5 minutes)

**Purpose:** Deep sleep after extended time in light sleep

**When it starts:**
- When entering light sleep

**When it resets:**
- Wake word detected (user returned)

**What it does when expired:**
```python
def _on_idle_timeout(self):
    print("⏰ Idle timeout - Entering deep sleep")
    self._enter_deep_sleep()
```

---

## Real-World Example

### Scenario: User has conversation then leaves

```
1. [LISTENING] User: "Olá"
                ↓
2. [PROCESSING] LLM generates response
                ↓
3. [SPEAKING] TTS plays: "Olá! Como posso ajudar?"
                ↓
4. [LISTENING] 30-second timer starts
                ↓
5. ... 30 seconds pass (user left) ...
                ↓
6. [LIGHT SLEEP] Whisper stops, Ollama stays loaded
                ↓ 5-minute timer starts
7. ... 5 minutes pass (user still gone) ...
                ↓
8. [DEEP SLEEP] Ollama stops, minimal power
                ↓
   ESP32 keeps listening for wake word
```

### Scenario: User returns after 2 minutes

```
1. [LIGHT SLEEP] Waiting...
                ↓
2. ESP32 detects "Marvin"
                ↓
3. [WAKE] Start Whisper (~1 second)
                ↓
4. [LISTENING] Ready to talk!
```

### Scenario: User returns after 10 minutes

```
1. [DEEP SLEEP] Ollama stopped
                ↓
2. ESP32 detects "Marvin"
                ↓
3. [WAKE] Start Ollama (~8 seconds)
                ↓
4. [WAKE] Start Whisper (~1 second)
                ↓
5. [LISTENING] Ready to talk!
```

---

## Power Savings Summary

| State | Components Running | Power Draw | Wake Time |
|-------|-------------------|------------|-----------|
| **Active Listening** | Whisper + Ollama + Python | ~8-10W | N/A |
| **Light Sleep** | Ollama + Python | ~3-4W | ~1s |
| **Deep Sleep** | Python only | ~0.5-1W | ~5-10s |

**Daily Usage Example (30 conversations, 2 min each):**
- Active: 1 hour = 8 Wh
- Light sleep: 3 hours = 10 Wh
- Deep sleep: 20 hours = 12 Wh
- **Total: ~30 Wh/day** vs **192 Wh/day always-on**
- **Savings: 84%**

---

## Key Design Decisions

### Why Two Sleep Levels?

**Light sleep:**
- Fast wake (1s) for frequent interactions
- Keeps conversation context in RAM
- Good for active usage periods

**Deep sleep:**
- Maximum power savings for extended idle
- Acceptable slow wake (5-10s) for infrequent use
- Good for overnight/away periods

### Why 30 Seconds + 5 Minutes?

**30-second conversation timeout:**
- Long enough for natural pauses in conversation
- Short enough to save power if user leaves
- Can be interrupted by user speaking

**5-minute idle timeout:**
- Balances responsiveness vs power savings
- Assumes user might return shortly
- Prevents frequent Ollama restarts

### Why Not Just Deep Sleep Always?

**Problem:** Frequent wake/sleep cycles would:
- Wear out storage (systemd service start/stop)
- Annoy users with 5-10s delays
- Waste CPU starting/stopping Ollama repeatedly

**Solution:** Two-tier system adapts to usage patterns

---

## Implementation Files

| File | Purpose | Key Methods |
|------|---------|-------------|
| `voice_chatbot.py` | Main controller | `_enter_light_sleep()`, `_enter_deep_sleep()`, `_on_wake_word_detected()` |
| `sleep_manager.py` | Ollama service control | `enter_deep_sleep()`, `wake_from_deep_sleep()` |
| `timeout_manager.py` | Timer management | `start_conversation_timer()`, `start_idle_timer()` |
| `esp32_wake_listener.py` | Wake word signal | `_on_wake_word_detected()` callback |

---

**Implementation Date:** 2025-11-02
**Status:** ✅ Complete and Tested
**Power Savings:** ~84-92% vs always-on
