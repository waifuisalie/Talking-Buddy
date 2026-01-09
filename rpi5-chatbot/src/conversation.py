"""
Conversation management for the voice chatbot
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

class ConversationEntry:
    """Represents a single conversation entry"""

    def __init__(self, role: str, content: str, timestamp: Optional[float] = None):
        self.role = role  # 'user' or 'assistant'
        self.content = content
        self.timestamp = timestamp or time.time()
        self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationEntry":
        """Create from dictionary"""
        entry = cls(data["role"], data["content"], data.get("timestamp"))
        entry.metadata = data.get("metadata", {})
        return entry

    def get_datetime(self) -> datetime:
        """Get datetime object from timestamp"""
        return datetime.fromtimestamp(self.timestamp)

    def get_age_minutes(self) -> float:
        """Get age of entry in minutes"""
        return (time.time() - self.timestamp) / 60

class ConversationManager:
    """Manages conversation history and context"""

    def __init__(self, max_entries: int = 50, save_file: Optional[str] = None):
        self.max_entries = max_entries
        self.save_file = save_file
        self.entries: List[ConversationEntry] = []
        self.session_id = str(int(time.time()))

        # Load existing conversation if save file exists
        if save_file and Path(save_file).exists():
            self.load_conversation()

    def add_entry(self, role: str, content: str, metadata: Optional[Dict] = None) -> ConversationEntry:
        """Add a new conversation entry"""
        entry = ConversationEntry(role, content)
        if metadata:
            entry.metadata.update(metadata)

        self.entries.append(entry)

        # Trim if too many entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        # Auto-save if configured
        if self.save_file:
            self.save_conversation()

        return entry

    def add_user_message(self, content: str, metadata: Optional[Dict] = None) -> ConversationEntry:
        """Add a user message"""
        return self.add_entry("user", content, metadata)

    def add_assistant_message(self, content: str, metadata: Optional[Dict] = None) -> ConversationEntry:
        """Add an assistant message"""
        return self.add_entry("assistant", content, metadata)

    def get_recent_entries(self, count: int = 10) -> List[ConversationEntry]:
        """Get the most recent conversation entries"""
        return self.entries[-count:] if self.entries else []

    def get_context_for_llm(self, max_entries: int = 8) -> List[Dict[str, str]]:
        """Get conversation context formatted for LLM"""
        recent_entries = self.get_recent_entries(max_entries)
        return [{"role": entry.role, "content": entry.content} for entry in recent_entries]

    def get_context_text(self, max_entries: int = 6) -> str:
        """Get conversation context as formatted text"""
        recent_entries = self.get_recent_entries(max_entries)
        if not recent_entries:
            return ""

        context_lines = []
        for entry in recent_entries:
            role = entry.role.title()
            context_lines.append(f"{role}: {entry.content}")

        return "\n".join(context_lines)

    def clear_history(self):
        """Clear all conversation history"""
        self.entries.clear()
        if self.save_file:
            self.save_conversation()
        print("🧹 Conversation history cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get conversation statistics"""
        if not self.entries:
            return {"total_entries": 0, "user_messages": 0, "assistant_messages": 0}

        user_count = sum(1 for entry in self.entries if entry.role == "user")
        assistant_count = sum(1 for entry in self.entries if entry.role == "assistant")

        first_entry = self.entries[0] if self.entries else None
        last_entry = self.entries[-1] if self.entries else None

        return {
            "total_entries": len(self.entries),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "session_id": self.session_id,
            "first_message_time": first_entry.get_datetime().isoformat() if first_entry else None,
            "last_message_time": last_entry.get_datetime().isoformat() if last_entry else None,
            "conversation_duration_minutes": (
                (last_entry.timestamp - first_entry.timestamp) / 60
                if first_entry and last_entry else 0
            )
        }

    def search_entries(self, query: str, case_sensitive: bool = False) -> List[ConversationEntry]:
        """Search conversation entries by content"""
        results = []
        search_query = query if case_sensitive else query.lower()

        for entry in self.entries:
            content = entry.content if case_sensitive else entry.content.lower()
            if search_query in content:
                results.append(entry)

        return results

    def get_entries_by_timeframe(self, minutes_ago: int) -> List[ConversationEntry]:
        """Get entries from a specific timeframe"""
        cutoff_time = time.time() - (minutes_ago * 60)
        return [entry for entry in self.entries if entry.timestamp >= cutoff_time]

    def export_conversation(self, format: str = "json") -> str:
        """Export conversation in different formats"""
        if format == "json":
            return self._export_json()
        elif format == "text":
            return self._export_text()
        elif format == "markdown":
            return self._export_markdown()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_json(self) -> str:
        """Export conversation as JSON"""
        data = {
            "session_id": self.session_id,
            "export_time": datetime.now().isoformat(),
            "stats": self.get_stats(),
            "entries": [entry.to_dict() for entry in self.entries]
        }
        return json.dumps(data, indent=2)

    def _export_text(self) -> str:
        """Export conversation as plain text"""
        lines = [f"Conversation Session: {self.session_id}"]
        lines.append(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 50)
        lines.append("")

        for entry in self.entries:
            timestamp = entry.get_datetime().strftime("%H:%M:%S")
            role = entry.role.title()
            lines.append(f"[{timestamp}] {role}: {entry.content}")

        return "\n".join(lines)

    def _export_markdown(self) -> str:
        """Export conversation as Markdown"""
        lines = [f"# Conversation Session: {self.session_id}"]
        lines.append(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        current_date = None
        for entry in self.entries:
            entry_date = entry.get_datetime().date()
            if current_date != entry_date:
                current_date = entry_date
                lines.append(f"## {entry_date.strftime('%Y-%m-%d')}")
                lines.append("")

            timestamp = entry.get_datetime().strftime("%H:%M:%S")
            role = "🗣️ **User**" if entry.role == "user" else "🤖 **Assistant**"
            lines.append(f"### {timestamp} - {role}")
            lines.append(f"{entry.content}")
            lines.append("")

        return "\n".join(lines)

    def save_conversation(self):
        """Save conversation to file"""
        if not self.save_file:
            return

        try:
            # Ensure directory exists
            Path(self.save_file).parent.mkdir(parents=True, exist_ok=True)

            # Save as JSON
            with open(self.save_file, 'w', encoding='utf-8') as f:
                f.write(self._export_json())

            print(f"💾 Conversation saved to {self.save_file}")

        except Exception as e:
            print(f"❌ Error saving conversation: {e}")

    def load_conversation(self):
        """Load conversation from file"""
        if not self.save_file or not Path(self.save_file).exists():
            return

        try:
            with open(self.save_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load entries
            self.entries = [ConversationEntry.from_dict(entry_data)
                          for entry_data in data.get("entries", [])]

            # Load session info if available
            if "session_id" in data:
                self.session_id = data["session_id"]

            print(f"📂 Loaded {len(self.entries)} conversation entries from {self.save_file}")

        except Exception as e:
            print(f"❌ Error loading conversation: {e}")

    def cleanup_old_entries(self, max_age_hours: int = 24):
        """Remove entries older than specified hours"""
        cutoff_time = time.time() - (max_age_hours * 3600)
        original_count = len(self.entries)

        self.entries = [entry for entry in self.entries if entry.timestamp >= cutoff_time]

        removed_count = original_count - len(self.entries)
        if removed_count > 0:
            print(f"🧹 Removed {removed_count} old conversation entries")
            if self.save_file:
                self.save_conversation()

class ConversationSummarizer:
    """Creates summaries of conversation history"""

    @staticmethod
    def create_summary(entries: List[ConversationEntry], max_length: int = 200) -> str:
        """Create a summary of conversation entries"""
        if not entries:
            return "No conversation history."

        # Count message types
        user_count = sum(1 for e in entries if e.role == "user")
        assistant_count = sum(1 for e in entries if e.role == "assistant")

        # Get conversation timespan
        if len(entries) > 1:
            duration_minutes = (entries[-1].timestamp - entries[0].timestamp) / 60
            duration_text = f"over {duration_minutes:.1f} minutes"
        else:
            duration_text = "in a single exchange"

        # Extract key topics (simple keyword extraction)
        all_text = " ".join(entry.content for entry in entries if entry.role == "user")
        # Simple topic extraction could be enhanced with NLP

        summary = (f"Conversation with {user_count} user messages and "
                  f"{assistant_count} assistant responses {duration_text}.")

        return summary[:max_length]