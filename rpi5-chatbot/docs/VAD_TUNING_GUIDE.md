# Voice Activity Detection (VAD) Tuning Guide

## Quick Summary

**VAD threshold tuning is CRITICAL for accurate speech recognition!**

Your chatbot has a `silence_threshold` parameter (measured in RMS - Root Mean Square audio level) that determines when speech starts and stops being recorded.

### The Issue You Found
- **Default threshold**: 50 RMS (too high)
- **Your optimal threshold**: 30 RMS (perfect for your microphone)
- **Result**: Dramatic improvement in transcription accuracy

This is **NOT a bug** - it's a feature that needs to be calibrated to YOUR specific hardware and environment.

---

## What is VAD (Voice Activity Detection)?

VAD is the mechanism that decides: "Is the user speaking right now?"

It works by analyzing the **RMS (Root Mean Square)** audio level:
- Low RMS = Silence or background noise
- High RMS = Speech

The `silence_threshold` parameter sets the boundary between silence and speech.

### Example from Your Logs

```
🔊 RMS:   38.3 | Threshold: 50 | 🤫 silence    ← Your speech was BELOW threshold!
🔊 RMS:   53.5 | Threshold: 50 | 🗣️ SPEECH     ← Your speech was ABOVE threshold
```

**Problem with threshold 50**:
- When you spoke at RMS 38, it was marked as "silence" even though you were speaking
- This caused words to be cut off or entire phrases misrecognized

**Solution with threshold 30**:
- Both RMS 38 and 53 are now above threshold
- All your speech is captured completely
- Much better transcription accuracy

---

## How to Find YOUR Optimal Threshold

### Step 1: Run the Chatbot in Debug Mode
```bash
cd fucking_with_AI/chatbot/
python run_chatbot.py
```

The chatbot prints RMS levels every 2 seconds:
```
🔊 RMS:    2.9 | Threshold: 50 | 🤫 silence     ← Background noise level
🔊 RMS:   38.3 | Threshold: 50 | 🤫 silence     ← Your speech level (too low!)
🔊 RMS:   53.5 | Threshold: 50 | 🗣️ SPEECH      ← Your speech level (good)
🔊 RMS:   15.0 | Threshold: 50 | 🤫 silence     ← Between utterances
```

### Step 2: Observe Your RMS Range

Listen to the debug output and note:
1. **Silence RMS**: When you're not speaking (e.g., 2.9, 15.0)
2. **Speech RMS**: When you speak normally (e.g., 38.3, 53.5)

### Step 3: Calculate Optimal Threshold

**Recommended formula**:
```
Optimal Threshold = (Average Silence RMS) + (20-30% of speech RMS)

Example from your case:
- Average silence: ~5-15 RMS
- Average speech: ~40-50 RMS
- Margin above silence: ~20-30 RMS
→ Optimal threshold: 25-35 RMS (you found 30 works great!)
```

### Step 4: Update config.py

Edit `config.py` in the WhisperConfig section:

```python
@dataclass
class WhisperConfig:
    # ... other settings ...
    silence_threshold: int = 30  # RMS threshold for speech detection (change this!)
```

Change `30` to your optimal value and restart the chatbot.

### Step 5: Test and Iterate

1. Speak normally into the microphone
2. Check the debug output: all your speech should show 🗣️ SPEECH
3. If words are still cut off → lower threshold more
4. If recording too much noise → raise threshold slightly

---

## Understanding RMS Levels

RMS (Root Mean Square) measures audio signal strength:

| RMS Range | What It Means | Example |
|-----------|-------------|---------|
| 0-10 | Very quiet/silence | Room ambient noise, far from mic |
| 10-20 | Quiet | Whisper, distant speech |
| 20-40 | Normal speech | Normal conversation distance |
| 40-80 | Loud speech | Shouting, close to microphone |
| 80+ | Very loud | Feedback, loud noises |

**Your case**:
- Silence: RMS 2-15
- Normal speech: RMS 35-55
- Optimal threshold: RMS 30 (20% above average silence, below average speech)

---

## VAD Tuning for Different Scenarios

### Quiet Room (Low Background Noise)
- Can use lower threshold (25-30)
- Captures all speech clearly
- Less chance of false positives

### Noisy Environment
- Need higher threshold (40-50)
- Reduces false speech detection
- May cut off quiet speech

### Different Microphones

| Microphone Type | Typical Range | Suggested Threshold |
|-----------------|---------------|-------------------|
| USB Condenser | 30-60 RMS | 25-35 |
| Headset/Lavalier | 40-70 RMS | 35-45 |
| Built-in Laptop | 20-50 RMS | 20-30 |
| Professional | 50-100 RMS | 40-60 |

---

## Common VAD Problems and Solutions

### Problem 1: Words Being Cut Off
**Symptom**: Transcription shows fragments like "De morangos" instead of "Você gosta de morangos?"

**Cause**: Threshold too high, not capturing beginning/end of speech

**Solution**: Lower threshold by 5-10 RMS increments
```python
# Try reducing threshold
silence_threshold: int = 25  # Lower from 30
```

### Problem 2: Too Much Background Noise Recorded
**Symptom**: Microphone picks up background noise, AC hum, keyboard clicks

**Cause**: Threshold too low, treating noise as speech

**Solution**: Raise threshold slightly, or improve audio environment
```python
# Raise threshold
silence_threshold: int = 40  # Higher from 30
```

### Problem 3: Inconsistent Speech Detection
**Symptom**: Sometimes catches speech, sometimes misses it

**Cause**: Your speech volume varies, or acoustic environment changes

**Solution**:
- Find the "sweet spot" between silence and speech
- Test with different speaking volumes
- Consider adjusting mic gain if available

### Problem 4: False Positives (Noise Detected as Speech)
**Symptom**: "Speech detected" for door slams, coughs, etc.

**Cause**: Threshold too low

**Solution**: Raise threshold, improve microphone positioning
```python
silence_threshold: int = 35  # Increase from 30
```

---

## Other VAD Parameters

Beyond `silence_threshold`, there are two other important parameters:

### silence_duration (default: 1.5 seconds)
How long the audio must be silent before stopping recording.

```python
silence_duration: float = 1.5  # Seconds
```

**When to adjust**:
- **Lower (0.5-1.0)**: For fast back-and-forth conversation
- **Higher (2.0-3.0)**: For longer spoken sentences, pauses in speech

### min_audio_length (default: 0.5 seconds)
Minimum audio length to process (prevents processing tiny noise bursts).

```python
min_audio_length: float = 0.5  # Seconds
```

**When to adjust**:
- **Lower (0.3)**: Accept very short utterances ("Yes", "No")
- **Higher (1.0)**: Only process longer phrases

---

## Your Optimal Configuration

Based on your successful tuning, here's what you've determined:

```python
@dataclass
class WhisperConfig:
    # ... other settings ...

    # VAD (Voice Activity Detection) settings
    silence_threshold: int = 30      # ✅ Optimized for your microphone
    silence_duration: float = 1.5    # Good for normal conversation
    min_audio_length: float = 0.5    # Captures short responses
    debug_mode: bool = True          # Keeps showing RMS for monitoring
```

**Your Results**:
- ✅ Complete sentence capture: "Olá meu nome é Stefan"
- ✅ Clear question recognition: "Você gosta de morangos?"
- ✅ Complex utterances: "Também gosto de comer hambúrgueres"
- ✅ Short responses: "De carne"

---

## Fine-Tuning Tips

### Test Different Distances
```
1m from mic (close):        RMS 50-70
0.5m from mic (normal):     RMS 35-50  ← Your range
0.3m from mic (very close): RMS 70+
```

Find where you naturally speak → set threshold ~15 RMS below

### Test Different Volumes
```
Whisper:    RMS 15-25  (too quiet!)
Normal:     RMS 35-50  (good range) ← Your case
Loud:       RMS 60-80  (shouting)
```

Set threshold where normal speech is clearly above it

### Account for Background Noise
If your environment has:
- **AC hum**: Raises baseline RMS by 3-5
- **Street noise**: Raises baseline RMS by 5-10
- **Keyboard typing**: Spikes RMS by 10-20

Adjust threshold to be well above your environment's RMS floor.

---

## Monitoring and Adjustment

The chatbot shows real-time RMS values. Use this to monitor:

```
During silence between sentences:
🔊 RMS:    5.0 | Threshold: 30 | 🤫 silence     ← Good
🔊 RMS:   45.0 | Threshold: 30 | 🗣️ SPEECH      ← Good

During speech at threshold 30:
🔊 RMS:   28.0 | Threshold: 30 | 🤫 silence     ← Words cut off!
                                                 (Lower threshold)

All background noise triggering speech:
🔊 RMS:   35.0 | Threshold: 30 | 🗣️ SPEECH      ← False positive!
                                                 (Raise threshold)
```

---

## Documentation for Future Reference

### Your Calibration Data (Stefan's Setup)
- **Microphone**: Unknown (but now calibrated)
- **Environment**: Quiet room
- **Optimal Threshold**: 30 RMS
- **Speech Range**: 35-55 RMS
- **Silence Range**: 2-15 RMS
- **Success Rate**: Significantly improved after tuning

### How to Share This with Others
If others use your chatbot:
1. Have them run in debug mode
2. Note their RMS ranges
3. Calculate their optimal threshold
4. Update config.py accordingly

---

## Summary

✅ **VAD threshold is your most critical speech recognition parameter**
✅ **It's environment and hardware dependent - must be tuned for YOUR setup**
✅ **Use the debug output to find optimal values**
✅ **Lower threshold = captures more speech (risk: noise)**
✅ **Higher threshold = filters more noise (risk: cuts speech)**
✅ **Your optimal: 30 RMS - produces excellent results**

The fact that you discovered this by experimentation shows you understand the system deeply. Great debugging! 🎉

---

## Quick Reference Card

| Parameter | Default | Your Optimal | Meaning |
|-----------|---------|-------------|---------|
| `silence_threshold` | 50 | 30 | RMS level to trigger speech detection |
| `silence_duration` | 1.5s | 1.5s | How long silence before stop recording |
| `min_audio_length` | 0.5s | 0.5s | Minimum audio to process |

**To adjust**: Edit `config.py`, change `silence_threshold: int = 30`

**To verify**: Run chatbot, check RMS values in debug output

**To iterate**: Try different values, test, compare transcription quality
