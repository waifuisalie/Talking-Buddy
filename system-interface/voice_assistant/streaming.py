"""
Streaming TTS processing pipeline
Ported from rpi5-chatbot/src/voice_chatbot.py

SentenceDetector: detects sentence boundaries from streaming text chunks
StreamingTTSProcessor: pipes detected sentences through TTS and into audio queue
"""

from typing import Optional


class SentenceDetector:
    """Detects sentence boundaries from streaming text chunks"""

    def __init__(self, min_length: int = 30, max_length: int = 80):
        """
        Initialize sentence detector

        Args:
            min_length: Minimum characters before a sentence ending triggers a flush (default: 15)
            max_length: Maximum characters to buffer before force-flushing at a word boundary (default: 30)
        """
        self.buffer = ""
        self.sentence_endings = ('.', '!', '?', ':', ';')
        self.min_sentence_length = min_length
        self.max_sentence_length = max_length
        self.paragraph_break = '\n\n'

    def add_chunk(self, chunk: str):
        """
        Add a text chunk and return completed sentences

        Args:
            chunk: Text chunk from streaming LLM

        Returns:
            List of complete sentences (may be empty)
        """
        self.buffer += chunk
        sentences = []

        while True:
            # Force-flush if buffer exceeds max_length: split at last word boundary
            if len(self.buffer) >= self.max_sentence_length:
                cut = self.buffer.rfind(' ', 0, self.max_sentence_length)
                if cut == -1:
                    cut = self.max_sentence_length
                chunk_text = self.buffer[:cut].strip()
                if chunk_text:
                    sentences.append(chunk_text)
                self.buffer = self.buffer[cut:].strip()
                continue

            # Collect ALL sentence ending positions in the buffer
            ending_positions = set()
            for ending in self.sentence_endings:
                pos = 0
                while True:
                    pos = self.buffer.find(ending, pos)
                    if pos == -1:
                        break
                    ending_positions.add(pos)
                    pos += 1

            if not ending_positions:
                break

            # Scan endings earliest-to-latest, flush at the first one that
            # produces >= min_length chars.
            flushed = False
            for pos in sorted(ending_positions):
                potential_sentence = self.buffer[:pos + 1].strip()
                if len(potential_sentence) >= self.min_sentence_length:
                    sentences.append(potential_sentence)
                    self.buffer = self.buffer[pos + 1:].strip()
                    flushed = True
                    break

            if not flushed:
                break

        return sentences

    def flush(self):
        """
        Return remaining buffer as final sentence

        Returns:
            Remaining text as final sentence, or None if buffer is empty
        """
        if self.buffer.strip():
            final_sentence = self.buffer.strip()
            self.buffer = ""
            return final_sentence
        return None


class StreamingTTSProcessor:
    """Processes streaming LLM chunks into TTS audio queue"""

    def __init__(self, tts_engine, audio_player, min_sentence_length: int = 30):
        """
        Initialize streaming TTS processor

        Args:
            tts_engine: TTS instance (TTSClient or SupertonicTTSClient) with synthesize_to_temp()
            audio_player: HardwareAudioPlayer instance with queue support
            min_sentence_length: Minimum characters for sentence detection
        """
        self.tts = tts_engine
        self.audio_player = audio_player
        self.sentence_detector = SentenceDetector(min_sentence_length)
        self.full_response = ""

    def process_chunk(self, chunk: str):
        """
        Process a text chunk and synthesize completed sentences

        Args:
            chunk: Text chunk from streaming LLM
        """
        self.full_response += chunk

        sentences = self.sentence_detector.add_chunk(chunk)

        for sentence in sentences:
            print(f"🎙️ Synthesizing sentence ({len(sentence)} chars): {sentence[:80]}...")
            try:
                audio_file = self.tts.synthesize_to_temp(sentence)
                if audio_file:
                    metadata = {
                        "text": sentence,
                        "cleanup": True
                    }
                    self.audio_player.enqueue_audio(audio_file, metadata)
                    print(f"✅ Enqueued audio for sentence")
                else:
                    print(f"⚠️  Failed to synthesize sentence: {sentence[:50]}...")
            except Exception as e:
                print(f"❌ Error synthesizing sentence: {e}")

    def finalize(self):
        """Synthesize any remaining text in buffer"""
        final_sentence = self.sentence_detector.flush()
        if final_sentence:
            print(f"🎙️ Finalizing: synthesizing remaining buffer ({len(final_sentence)} chars): {final_sentence[:80]}...")
            try:
                audio_file = self.tts.synthesize_to_temp(final_sentence)
                if audio_file:
                    metadata = {
                        "text": final_sentence,
                        "cleanup": True
                    }
                    self.audio_player.enqueue_audio(audio_file, metadata)
                    print(f"✅ Enqueued final audio")
                else:
                    print(f"⚠️  Failed to synthesize final sentence: {final_sentence[:50]}...")
            except Exception as e:
                print(f"❌ Error synthesizing final sentence: {e}")
        else:
            print("ℹ️  No remaining text in buffer to finalize")

    def get_full_response(self) -> str:
        """Get the complete accumulated response text"""
        return self.full_response
