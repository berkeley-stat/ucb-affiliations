"""Live multi-line terminal status display, built on rich."""
import sys
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

# Braille spinner frames.
_SPINNER_CHARS = [
    "\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f",
]

# Static glyphs for settled states.
_STATE_DONE = {
    "succeeded": "\u2713",  # ✓
    "failed": "\u2717",  # ✗
    "skipped": "\u25b7",  # ▷
    "pending": "\u25f6",  # ◷
}


def _is_tty(stream) -> bool:
    """Best-effort check whether a stream is an interactive terminal."""
    try:
        return stream is not None and stream.isatty()
    except Exception:
        return False


class StatusDisplay:
    """A multi-line, in-place-updating status region for live per-system feedback.

    Uses rich's ``Live`` so cursor positioning, line clearing, and TTY
    detection are handled robustly.

    When disabled or not attached to a TTY, all methods are no-ops (used for
    scripting, web, ``--no-status``, json/bulk formats).

    Args:
        enabled: Whether to render at all.
        stream: The stream to write to. Defaults to stderr. Callers that
            redirect ``sys.stderr`` for flowtoy's benefit should pass the
            *original* stderr here so the live UI is not lost.
        interval: Redraw interval in seconds.
    """

    def __init__(self, enabled: bool = True, stream=None, interval: float = 0.1):
        self.stream = stream if stream is not None else sys.stderr
        self.interval = interval

        console = Console(file=self.stream, stderr=True)
        self.enabled = bool(enabled and _is_tty(self.stream) and console.is_terminal)
        self._console = console

        self._rows: dict = {}  # label -> state
        self._order: list = []  # insertion order of labels
        self._phase: str = ""
        self._running = False
        self._thread: threading.Thread = None
        self._lock = threading.RLock()
        self._frame = 0
        self._live: Live = None

    def start(self):
        """Begin rendering the live region."""
        if not self.enabled:
            return self
        with self._lock:
            if self._running:
                return self
            self._console = Console(file=self.stream, stderr=True)
            self._live = Live(
                self._renderable(),
                console=self._console,
                refresh_per_second=int(1.0 / self.interval) if self.interval else 10,
                transient=True,
            )
            self._live.start()
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def set_phase(self, text: str):
        """Set a single phase header line (e.g. 'Loading flow configuration')."""
        if not self.enabled:
            return
        with self._lock:
            self._phase = text
            self._refresh()

    def set_states(self, states: dict):
        """Replace all rows with a mapping of label -> state."""
        if not self.enabled:
            return
        with self._lock:
            for name, state in states.items():
                if name not in self._order:
                    self._order.append(name)
                self._rows[name] = state
            self._refresh()

    def set_state(self, name: str, state: str):
        """Update a single row's state."""
        if not self.enabled:
            return
        with self._lock:
            if name not in self._order:
                self._order.append(name)
            self._rows[name] = state
            self._refresh()

    def stop(self):
        """Clear the region and stop rendering."""
        if not self.enabled:
            return
        with self._lock:
            self._running = False
            thread = self._thread
            live = self._live
        if thread:
            thread.join(timeout=self.interval * 3)
        if live is not None:
            try:
                live.stop()  # transient=True clears the region
            except Exception:
                pass
        with self._lock:
            self._live = None
            self._rows = {}
            self._order = []
            self._phase = ""

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # --- internals ---

    def _renderable(self):
        parts = []
        if self._phase:
            parts.append(Text(self._phase))
        for label in self._order:
            state = self._rows.get(label, "pending")
            parts.append(Text(f"{self._glyph(state)} {label}"))
        return Group(*parts)

    def _glyph(self, state):
        if state == "running":
            return _SPINNER_CHARS[self._frame % len(_SPINNER_CHARS)]
        return _STATE_DONE.get(state, _STATE_DONE["pending"])

    def _refresh(self):
        if self._live is not None:
            self._live.update(self._renderable())

    def _run(self):
        while True:
            with self._lock:
                if not self._running:
                    break
                self._frame += 1
                self._refresh()
            time.sleep(self.interval)
