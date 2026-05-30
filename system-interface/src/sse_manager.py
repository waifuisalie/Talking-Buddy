"""
SSE (Server-Sent Events) session manager
Manages per-session event queues for real-time browser streaming
"""

import json
import queue
import threading
import uuid
import time
from typing import Dict, Generator, Optional


class SSEManager:
    """Thread-safe SSE session manager"""

    def __init__(self, session_timeout: float = 300.0):
        """
        Args:
            session_timeout: Seconds before idle sessions are cleaned up (default: 5 min)
        """
        self._sessions: Dict[str, queue.Queue] = {}
        self._session_times: Dict[str, float] = {}
        self._cancelled: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._session_timeout = session_timeout

    def create_session(self) -> str:
        """Create a new SSE session and return its ID"""
        session_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[session_id] = queue.Queue()
            self._session_times[session_id] = time.time()
            self._cancelled[session_id] = False
        return session_id

    def mark_cancelled(self, session_id: str) -> bool:
        """Flag a session as cancelled. Returns True if the session existed."""
        with self._lock:
            if session_id in self._sessions:
                self._cancelled[session_id] = True
                return True
            return False

    def is_cancelled(self, session_id: str) -> bool:
        """Cheap check used inside the streaming loop to abort mid-stream."""
        return self._cancelled.get(session_id, False)

    def push_event(self, session_id: str, event_type: str, data: dict):
        """
        Push an event to a session's queue

        Args:
            session_id: Target session
            event_type: SSE event name (e.g., 'text_chunk', 'sentence_playing', 'response_done')
            data: JSON-serializable data dict
        """
        with self._lock:
            q = self._sessions.get(session_id)
            if q is not None:
                q.put({
                    "event": event_type,
                    "data": data
                })
                self._session_times[session_id] = time.time()

    def stream_events(self, session_id: str) -> Generator[str, None, None]:
        """
        Yield SSE-formatted strings for a session (blocking generator)

        Terminates when a 'response_done' or 'error' event is sent,
        or when the session is closed.
        """
        with self._lock:
            q = self._sessions.get(session_id)

        if q is None:
            yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        while True:
            try:
                item = q.get(timeout=30.0)  # 30s heartbeat timeout

                event_type = item["event"]
                data_json = json.dumps(item["data"], ensure_ascii=False)

                yield f"event: {event_type}\ndata: {data_json}\n\n"

                # Terminal events — close the stream
                if event_type in ('response_done', 'error'):
                    break

            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"

                # Check if session still exists
                with self._lock:
                    if session_id not in self._sessions:
                        break

    def close_session(self, session_id: str):
        """Remove a session and its queue"""
        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_times.pop(session_id, None)
            self._cancelled.pop(session_id, None)

    def cleanup_stale_sessions(self):
        """Remove sessions older than timeout"""
        now = time.time()
        with self._lock:
            stale = [
                sid for sid, t in self._session_times.items()
                if now - t > self._session_timeout
            ]
            for sid in stale:
                self._sessions.pop(sid, None)
                self._session_times.pop(sid, None)
                self._cancelled.pop(sid, None)
            if stale:
                print(f"🧹 [SSE] Cleaned up {len(stale)} stale sessions")

    @property
    def active_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)
