"""
scaffy_pet.py — Scaffy: Proactive Local AI Desktop Reading Companion
=====================================================================
A self-contained PyQt6 desktop pet that proactively assists readers:
  1. Word Hover Dwell (5.0s): Detects when the cursor stays stationary
     (within 5px) over an external word, selects it, and explains it.
  2. Paragraph Reading Friction (20.0s): Detects reading stalls where
     the mouse moves slowly within the same vertical band, selects the
     paragraph, and breaks down the core concepts.
  3. Manual Ctrl+C Backup Trigger: Actively polls the clipboard so
     standard manual copying always works seamlessly.
  4. Pet Interactivity & Gamification (Feature Set 2):
     - Rapid Petting Interaction: Stroking the mascot triggers a 'petted'
       purr state with happy closed eyes (^ ^), intense pink blush,
       floating hearts (♥), and soft purring audio.
     - Double-Click Reaction: Triggers a celebratory 360° backflip
       mini-animation with cheerful reading encouragement tips.
     - Audio Feedback: Non-blocking winsound audio queue (gentle high chime
       on ready, soft purr on petting, low chirp on thinking, mute button
       in bubble header + right-click context menu).

Hardware target : 12th-Gen i5 / 8 GB RAM / Intel iGPU (no CUDA)
Model           : qwen2.5-0.5b-instruct-q4_k_m.gguf
Frameworks      : PyQt6, pyautogui, pyperclip, llama-cpp-python
Platform        : Windows 11

Run:  python scaffy_pet.py
"""

# ── Standard library ──────────────────────────────────────────────
import sys
import os
import json
import re
import time
import math
import ctypes
import winsound
import wave
import struct
import io
import queue
import threading
import random

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Third-party ───────────────────────────────────────────────────
import pyperclip
import pyautogui
from llama_cpp import Llama
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QRect
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QMenu,
)
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath

# Disable PyAutoGUI corner failsafe to prevent crashes at screen edges
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02

# ── Qt environment ────────────────────────────────────────────────
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"


# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# Path to the GGUF model (same directory as this script)
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "qwen2.5-0.5b-instruct-q4_k_m.gguf",
)

# FIX #1a: Context window increased from 1024 → 2048 to avoid
# "Requested tokens exceed context window" errors.
MODEL_CTX   = 2048
MODEL_THREADS = 6

# FIX #1b: Hard ceiling on input snippet length (characters).
# With ChatML framing + system prompt overhead (~350 tokens), 1200
# characters of user text keeps total prompt safely under ~1500 tokens,
# leaving ≥500 tokens for generation inside the 2048 context.
MAX_SNIPPET_CHARS = 1200

# Maximum tokens the model may generate per request.
MAX_GENERATION_TOKENS = 300

# LLM sampling parameters.
TEMPERATURE = 0.3


# ═══════════════════════════════════════════════════════════════════
#  AUDIO & GAMIFICATION (Feature Set 2)
# ═══════════════════════════════════════════════════════════════════

ENCOURAGEMENT_TIPS = [
    "🌟 You're doing amazing! Digesting hard papers one intuition at a time builds real mastery.",
    "💡 Pro Tip: When stuck on math, replace Greek symbols with physical real-world nouns!",
    "☕ Hydration check! Reading dense technical docs is heavy mental lifting. Take a deep breath.",
    "🚀 Every giant transformer or neural network is just matrix multiplications in a trench coat!",
    "🧠 Cognitive intuition beats rote memorization every single time. Keep questioning!",
    "🐾 I'm right here in your corner. Highlight any confusing word or paragraph and I'll break it down!",
    "🎯 Struggling with a concept means your brain is actively laying down new neural pathways!",
    "📚 The best researchers re-read confusing paragraphs 3 to 5 times. Pacing is power!",
    "✨ Don't let notation intimidate you—most complex equations are simple ideas in formal disguise.",
    "🔬 Curiosity is your superpower. Every expert was once a beginner staring at a baffling paper.",
    "🐱 Purr-fect focus! Remember to relax your shoulders and unclench your jaw while reading.",
    "⚡ Break complex mechanisms into: 1) What comes in, 2) What changes, 3) What comes out.",
    "🌱 Learning happens at the edge of comfort. If it feels challenging, you are leveling up!",
    "🎨 Try drawing a mini mental sketch of the data flow when an algorithm seems dense.",
    "🏆 One deep paper understood is worth fifty skimmed. You're building deep knowledge!",
    "🔍 Whenever you see an unfamiliar acronym, assume it's just a shorthand label, not magic.",
    "🔥 Momentum is built one sentence at a time. Keep reading, you've got this!",
    "📖 Great code and great breakthroughs always start with patient, careful reading.",
    "💫 Take pride in being someone who reads the original source material. That's true engineering!",
    "☕ Cozy study session in progress. Scaffy is cheering for you with every page turned!",
]


def _generate_cat_meow(volume: float = 0.28) -> bytes:
    """Synthesize a soft, realistic cat meow with rising-falling vocal tract formants."""
    sample_rate = 44100
    duration = 0.45
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            # Vocal pitch contour: starts at 460Hz, rises to 680Hz, softens to 500Hz
            if t < 0.18:
                freq = 460 + (680 - 460) * (t / 0.18) ** 0.8
            else:
                freq = 680 - (680 - 500) * ((t - 0.18) / (duration - 0.18)) ** 1.1
            # Amplitude envelope
            if t < 0.06:
                amp = t / 0.06
            elif t > 0.32:
                amp = max(0.0, (duration - t) / (duration - 0.32))
            else:
                amp = 1.0
            vibrato = 1.0 + 0.025 * math.sin(2 * math.pi * 6.0 * t)
            f = freq * vibrato
            # Feline voice harmonics (Fundamental + 2nd + 3rd harmonic)
            val = (
                0.62 * math.sin(2 * math.pi * f * t)
                + 0.28 * math.sin(2 * math.pi * 2 * f * t)
                + 0.10 * math.sin(2 * math.pi * 3 * f * t)
            )
            sample = int(32767 * volume * amp * val)
            frames.extend(struct.pack("<h", max(-32767, min(32767, sample))))
        w.writeframes(frames)
    return buf.getvalue()


def _generate_cat_purr(volume: float = 0.28) -> bytes:
    """Synthesize authentic 26Hz amplitude-modulated low purring vibration."""
    sample_rate = 44100
    duration = 0.60
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            purr_pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 26 * t)
            val = 0.70 * math.sin(2 * math.pi * 92 * t) + 0.30 * math.sin(2 * math.pi * 184 * t)
            amp = purr_pulse * math.sin(math.pi * (t / duration)) ** 0.5
            sample = int(32767 * volume * amp * val)
            frames.extend(struct.pack("<h", max(-32767, min(32767, sample))))
        w.writeframes(frames)
    return buf.getvalue()


def _generate_cat_mrrp(volume: float = 0.26) -> bytes:
    """Synthesize a friendly cat trill / 'mrrp' greeting sound."""
    sample_rate = 44100
    duration = 0.25
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            freq = 440 + 320 * (t / duration)
            vibrato = 1.0 + 0.04 * math.sin(2 * math.pi * 26 * t)
            amp = math.sin(math.pi * (t / duration)) ** 0.7
            val = 0.75 * math.sin(2 * math.pi * freq * vibrato * t) + 0.25 * math.sin(4 * math.pi * freq * vibrato * t)
            sample = int(32767 * volume * amp * val)
            frames.extend(struct.pack("<h", max(-32767, min(32767, sample))))
        w.writeframes(frames)
    return buf.getvalue()


def _generate_cat_chirp(volume: float = 0.20) -> bytes:
    """Synthesize a soft, quiet inquisitive kitten chirp."""
    sample_rate = 44100
    duration = 0.12
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            freq = 560 + 200 * (t / duration)
            amp = math.sin(math.pi * (t / duration))
            val = math.sin(2 * math.pi * freq * t)
            sample = int(32767 * volume * amp * val)
            frames.extend(struct.pack("<h", max(-32767, min(32767, sample))))
        w.writeframes(frames)
    return buf.getvalue()


class SoundManager:
    """Thread-safe background audio manager using cute synthesized cat vocal sounds.
    Non-blocking: requests are dispatched to a daemon worker thread so the GUI never stutters."""

    def __init__(self) -> None:
        self.muted = False
        self._queue: queue.Queue[str | None] = queue.Queue()

        # Pre-synthesize all cozy cat sounds into memory for instant 0ms latency playback
        mrrp_wav = _generate_cat_mrrp(volume=0.26)
        purr_wav = _generate_cat_purr(volume=0.28)
        meow_wav = _generate_cat_meow(volume=0.28)
        chirp_wav = _generate_cat_chirp(volume=0.18)

        self._sounds: dict[str, bytes] = {
            "mrrp": mrrp_wav,              # Friendly trill when explanation is ready
            "chime": mrrp_wav,             # Alias for ready notification
            "purr": purr_wav,              # Authentic 26Hz purr rumble when petted
            "meow": meow_wav,              # Cheerful soft meow on celebration
            "flip": meow_wav,              # Alias for celebration flip
            "chirp": chirp_wav,            # Inquisitive soft chirp when thinking starts
            "unmute_confirm": mrrp_wav,
        }

        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def play(self, sound_name: str) -> None:
        if not self.muted:
            self._queue.put(sound_name)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if not self.muted:
            self._queue.put("unmute_confirm")
        return self.muted

    def _worker(self) -> None:
        while True:
            sound = self._queue.get()
            if sound is None:
                break
            if not self.muted:
                try:
                    wav_data = self._sounds.get(sound)
                    if wav_data:
                        winsound.PlaySound(wav_data, winsound.SND_MEMORY)
                except Exception:
                    pass
            self._queue.task_done()


# ═══════════════════════════════════════════════════════════════════
#  SESSION HISTORY CACHE  (FIX #4)
# ═══════════════════════════════════════════════════════════════════
# Simple in-memory list of {"snippet": ..., "result": {...}} dicts.
# Before running inference we check if the new clipboard text is an
# exact match *or* a substantial substring of a previously-explained
# snippet, and return the cached result immediately.

session_history: list[dict] = []


def _find_cached(snippet: str) -> dict | None:
    """Return a cached result dict if `snippet` matches or is closely
    related to a previously-explained snippet, else None.

    "Closely related" is defined as:
      • exact match, OR
      • the new snippet is a substring (≥60 % of the cached length), OR
      • the cached snippet is a substring (≥60 % of the new length).
    This avoids re-running CPU inference when the user re-copies the
    same paragraph or a slightly trimmed version of it.
    """
    snippet_lower = snippet.lower().strip()
    for entry in reversed(session_history):  # most-recent first
        cached_lower = entry["snippet"].lower().strip()
        # Exact match
        if snippet_lower == cached_lower:
            return entry["result"]
        # Substantial overlap check
        shorter, longer = sorted(
            [snippet_lower, cached_lower], key=len
        )
        if shorter and shorter in longer and len(shorter) >= 0.6 * len(longer):
            return entry["result"]
    return None


def _cache_result(snippet: str, result: dict) -> None:
    """Append a new entry to session history (bounded at 50 items)."""
    session_history.append({"snippet": snippet, "result": result})
    # Keep memory bounded
    if len(session_history) > 50:
        session_history.pop(0)


# ═══════════════════════════════════════════════════════════════════
#  LLM ENGINE INITIALISATION
# ═══════════════════════════════════════════════════════════════════

print("🐾 Initializing Scaffy CPU Engine...")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=MODEL_CTX,          # FIX #1a
    n_threads=MODEL_THREADS,
    n_gpu_layers=0,           # CPU-only, no CUDA
    verbose=False,
)
print("✨ Engine Ready!")


# ═══════════════════════════════════════════════════════════════════
#  PROMPT & INFERENCE  (FIX #3)
# ═══════════════════════════════════════════════════════════════════

# FIX #3a: Official Qwen ChatML prompt structure with a concrete
# one-shot example. Tiny models (0.5B) copy placeholder text literally,
# so every field in the example contains real concrete content.
# Explicitly forbid echoing template placeholders or instructions.
SYSTEM_PROMPT = """\
You are Scaffy, a master technical reading tutor and computing expert.
When given a paragraph, technical passage, or single word, explain the core concepts clearly and concisely.
If the input is a multi-sentence paragraph or complex excerpt, summarize the essential takeaway in the concept and provide an intuitive breakdown.
If the input is only 1 or 2 words (e.g. "crashes", "deadlock", "gradient"), define and demystify that technical computing or machine learning concept immediately.
Never echo template phrases, placeholder words, or prompt instructions.

You must respond with ONLY a single raw JSON object matching this real example:

User input: "softmax(z_i) = exp(z_i) / sum(exp(z_j))"
Your reply:
{"concept": "Softmax Function", "analogy": "Like converting test scores into percentages so the whole class adds up to 100 percent.", "example": "softmax([2.0, 1.0, 0.1]) -> [0.659, 0.242, 0.099]", "code": "probs = np.exp(z) / np.exp(z).sum()"}

Now explain the user's input:"""


def _build_chatml_prompt(snippet: str) -> str:
    """Construct a Qwen ChatML prompt with system + user + assistant
    turn opener so the model starts generating the JSON directly."""
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n"
        f'Explain this snippet:\n"""{snippet}"""<|im_end|>\n'
        f"<|im_start|>assistant\n"
    )


def _parse_llm_json(raw: str) -> dict:
    """FIX #3b: Robustly extract a JSON dict from potentially messy
    model output.

    Strategy:
      1. Try json.loads on the whole string (fast path).
      2. Regex-extract the first {...} block and try again.
      3. Regex-extract individual key:"value" pairs as last resort.
      4. Return the raw text stuffed into the 'analogy' field if all
         else fails — the UI never crashes.
    """
    # --- Fast path: clean JSON ─────────────────────────────────────
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _normalise_keys(parsed)
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Regex: extract first { ... } block ────────────────────────
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        # Try greedy match in case of nested braces from code field
        match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return _normalise_keys(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    # --- Last-resort regex: pull individual fields ─────────────────
    result: dict[str, str] = {}
    for key in ("concept", "analogy", "example", "code"):
        # Match "key": "value" allowing escaped quotes inside value
        pat = rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        m = re.search(pat, raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace('\\"', '"').replace("\\n", "\n")
    if result:
        return _normalise_keys(result)

    # --- Total fallback: stuff raw text into analogy ───────────────
    return {
        "concept": "Concept Overview",
        "analogy": raw.strip() or "(no output)",
        "example": "",
        "code": "",
    }


def _normalise_keys(d: dict) -> dict:
    """Ensure the returned dict always has all four expected keys,
    falling back to empty strings for any missing field."""
    return {
        "concept": str(d.get("concept", "Concept Overview")).strip(),
        "analogy": str(d.get("analogy", "")).strip(),
        "example": str(d.get("example", "")).strip(),
        "code":    str(d.get("code", "")).strip(),
    }


def generate_scaffold(snippet: str) -> dict:
    """Run local CPU inference and return a structured explanation dict.

    The snippet is already truncated by the caller, but we guard here
    too for defence-in-depth.
    """
    # Defence-in-depth truncation (FIX #1b)
    snippet = snippet[:MAX_SNIPPET_CHARS]

    prompt = _build_chatml_prompt(snippet)

    output = llm(
        prompt,
        max_tokens=MAX_GENERATION_TOKENS,
        temperature=TEMPERATURE,
        stop=["<|im_end|>", "\n\n\n"],
    )

    raw = output["choices"][0]["text"].strip()
    return _parse_llm_json(raw)


# ═══════════════════════════════════════════════════════════════════
#  BACKGROUND WORKER  (QThread — UI never freezes)
# ═══════════════════════════════════════════════════════════════════

class BrainWorker(QThread):
    """Runs LLM inference off the main thread, emits a dict signal."""

    finished = pyqtSignal(dict)

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def run(self) -> None:
        try:
            # Check session cache first (FIX #4)
            cached = _find_cached(self.text)
            if cached is not None:
                self.finished.emit(cached)
                return

            result = generate_scaffold(self.text)
            _cache_result(self.text, result)
            self.finished.emit(result)
        except Exception as exc:
            self.finished.emit({
                "concept": "⚠ Notice",
                "analogy": f"Inference error: {exc}",
                "example": "",
                "code": "",
            })


class ProactiveSensorThread(QThread):
    """Non-blocking background sensor tracking mouse coordinates and text highlights
    to proactively assist readers on PDFs, research papers, and technical articles.

    Features:
      1. Highlight Drag-Release Capture (Instant):
         - When user selects any word, sentence, or paragraph with the mouse and releases
           the left button, Scaffy immediately copies the selected text WITHOUT clicking,
           preserving the reader's visual highlight on screen.
      2. Context Awareness & Suppression:
         - Ignores cursor movements in browser tab bars, URL bars, ribbons, and taskbars.
         - Suppresses auto-selection while the user is typing, switching tabs, or using shortcuts.
      3. Word Hover Dwell (5.0s):
         - Triggers when cursor is held stationary (<=4.0px) on a single technical term.
         - First checks if text is already selected (non-destructive); if not, double-clicks word.
      4. Paragraph Reading Friction (15.0s):
         - Tracks reading pacing across lines within the same paragraph vertical band (+/-95px).
         - First checks if text is already selected; if not, selects paragraph or term to explain.
    """

    text_detected = pyqtSignal(str, str)  # (text, "selection" | "word_hover" | "paragraph_friction")

    WORD_DWELL_SECONDS = 5.0
    WORD_THRESHOLD_PX = 4.0

    PARAGRAPH_DWELL_SECONDS = 15.0
    PARAGRAPH_BAND_PX = 95.0

    POLL_INTERVAL_SEC = 0.08

    def __init__(self, is_over_scaffy_fn, is_busy_fn) -> None:
        super().__init__()
        self.is_over_scaffy = is_over_scaffy_fn
        self.is_busy = is_busy_fn
        self._running = True

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _is_user_typing() -> bool:
        """Check if any typing/editing keys are currently being pressed."""
        # A-Z, 0-9, Backspace, Enter, Space, Tab, Delete
        keys = list(range(0x41, 0x5B)) + list(range(0x30, 0x3A)) + [0x08, 0x0D, 0x20, 0x09, 0x2E]
        for vk in keys:
            if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                return True
        return False

    @staticmethod
    def _get_foreground_window() -> tuple[int, str]:
        """Get the HWND and title of the currently focused window."""
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        return hwnd, title

    @staticmethod
    def _grab_current_selection_without_clicking() -> str:
        """Non-destructively copy whatever is currently selected in the active window.
        Uses Win32 keybd_event to send Ctrl+C without clicking or modifying the visual highlight."""
        old_clip = ""
        try:
            old_clip = pyperclip.paste()
        except Exception:
            pass

        VK_CONTROL = 0x11
        KEY_C = 0x43
        KEYEVENTF_KEYUP = 0x0002

        try:
            # Clear clipboard to detect if active selection exists
            pyperclip.copy("")
            time.sleep(0.02)

            # Synthesize Ctrl+C
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            ctypes.windll.user32.keybd_event(KEY_C, 0, 0, 0)
            time.sleep(0.04)
            ctypes.windll.user32.keybd_event(KEY_C, 0, KEYEVENTF_KEYUP, 0)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.06)

            new_clip = pyperclip.paste().strip()
            if (
                new_clip
                and len(new_clip) >= 3
                and not new_clip.startswith("UpdateLayeredWindow")
                and not new_clip.startswith("PS C:")
            ):
                return new_clip
            else:
                # Restore previous clipboard if nothing was selected
                if old_clip:
                    pyperclip.copy(old_clip)
                return ""
        except Exception:
            if old_clip:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass
            return ""

    def _grab_selection(self, x: int, y: int, mode: str) -> str:
        """Fallback automated selection when no text was selected beforehand."""
        try:
            if mode == "word":
                pyautogui.doubleClick(x, y)
                time.sleep(0.06)
                return self._grab_current_selection_without_clicking()
            else:
                # Triple click for paragraph selection
                pyautogui.tripleClick(x, y)
                time.sleep(0.06)
                text = self._grab_current_selection_without_clicking()
                if not text or len(text) < 15:
                    # Fallback: double click to get the term
                    pyautogui.doubleClick(x, y)
                    time.sleep(0.06)
                    text = self._grab_current_selection_without_clicking()
                return text
        except Exception:
            return ""

    def run(self) -> None:
        word_anchor = None
        word_dwell_start = time.time()
        word_triggered = False

        para_anchor_y = None
        para_dwell_start = time.time()
        para_triggered = False
        last_pos = None

        last_typing_time = 0.0
        last_hwnd = 0
        last_title = ""
        last_window_switch = time.time()

        # Mouse drag tracking for instant highlight release capture
        was_lbutton_down = False
        drag_start_pos: tuple[int, int] | None = None
        max_drag_dist: float = 0.0

        while self._running:
            time.sleep(self.POLL_INTERVAL_SEC)
            if not self._running:
                break

            now = time.time()

            # ── 1. Typing Detection (Suppress while user is writing/coding) ──
            try:
                if self._is_user_typing():
                    last_typing_time = now
                if now - last_typing_time < 2.2:
                    word_dwell_start = now
                    para_dwell_start = now
                    continue
            except Exception:
                pass

            # ── 2. Active Window / Tab Switching Detection ───────
            try:
                curr_hwnd, curr_title = self._get_foreground_window()
                if curr_hwnd != last_hwnd or curr_title != last_title:
                    last_hwnd = curr_hwnd
                    last_title = curr_title
                    last_window_switch = now
                    word_anchor = None
                    para_anchor_y = None
                    word_triggered = False
                    para_triggered = False
                    was_lbutton_down = False
                    drag_start_pos = None
                    max_drag_dist = 0.0

                if now - last_window_switch < 1.2:
                    continue
            except Exception:
                pass

            # ── 3. Query Mouse Position & Screen Boundaries ──────
            try:
                pos = pyautogui.position()
                cx, cy = int(pos.x), int(pos.y)
                screen_w, screen_h = pyautogui.size()
            except Exception:
                continue

            # ── 4. Exclude Non-Reading UI Chrome (Tabs, Address Bars, Taskbar) ─
            if cy < 110 or cy > screen_h - 45 or cx < 15 or cx > screen_w - 15:
                word_dwell_start = now
                para_dwell_start = now
                was_lbutton_down = False
                drag_start_pos = None
                max_drag_dist = 0.0
                continue

            # ── 5. Self-Window Exclusion ─────────────────────────
            try:
                if self.is_over_scaffy(cx, cy):
                    word_anchor = (cx, cy)
                    word_dwell_start = now
                    para_anchor_y = cy
                    para_dwell_start = now
                    last_pos = (cx, cy)
                    was_lbutton_down = False
                    drag_start_pos = None
                    max_drag_dist = 0.0
                    continue
            except Exception:
                pass

            # ── 6. Mouse Drag & Highlight Release Detection ──────
            try:
                lbutton_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
                rbutton_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000)

                if lbutton_down:
                    if not was_lbutton_down:
                        # Drag started
                        was_lbutton_down = True
                        drag_start_pos = (cx, cy)
                        max_drag_dist = 0.0
                    else:
                        if drag_start_pos:
                            cur_dist = math.hypot(cx - drag_start_pos[0], cy - drag_start_pos[1])
                            max_drag_dist = max(max_drag_dist, cur_dist)

                    # Reset dwell timers while dragging
                    word_dwell_start = now
                    para_dwell_start = now
                    continue

                elif was_lbutton_down:
                    # Mouse button was JUST released!
                    was_lbutton_down = False
                    if max_drag_dist >= 12.0:
                        # User completed a mouse drag text selection!
                        if not self.is_busy():
                            time.sleep(0.08)  # Allow target app to finalize selection highlight
                            text = self._grab_current_selection_without_clicking()
                            if text and len(text) >= 3:
                                self.text_detected.emit(text, "selection")
                                word_triggered = True
                                para_triggered = True
                                word_dwell_start = now
                                para_dwell_start = now

                    drag_start_pos = None
                    max_drag_dist = 0.0

                if rbutton_down:
                    word_dwell_start = now
                    para_dwell_start = now
                    continue
            except Exception:
                pass

            if word_anchor is None:
                word_anchor = (cx, cy)
                word_dwell_start = now
            if para_anchor_y is None:
                para_anchor_y = cy
                para_dwell_start = now
            if last_pos is None:
                last_pos = (cx, cy)

            # ── 7. Word Hover Dwell (Stationary <= 4.0px for 5.0s) ─
            dist_word = math.hypot(cx - word_anchor[0], cy - word_anchor[1])
            if dist_word <= self.WORD_THRESHOLD_PX:
                dwell_duration = now - word_dwell_start
                if dwell_duration >= self.WORD_DWELL_SECONDS and not word_triggered:
                    if not self.is_busy():
                        word_triggered = True
                        # Step 1: Check if user already highlighted text (non-destructive)
                        text = self._grab_current_selection_without_clicking()
                        # Step 2: Fallback to selecting word under cursor if nothing was selected
                        if not text:
                            text = self._grab_selection(cx, cy, mode="word")
                        if text and len(text) >= 3:
                            self.text_detected.emit(text, "word_hover")
            else:
                word_anchor = (cx, cy)
                word_dwell_start = now
                if dist_word > 15:
                    word_triggered = False

            # ── 8. Paragraph Reading Friction (15.0s in vertical reading band) ─
            y_diff = abs(cy - para_anchor_y)

            # Continuous reading motion: as long as cursor stays in paragraph band (+/-95px)
            if y_diff <= self.PARAGRAPH_BAND_PX:
                para_duration = now - para_dwell_start
                if para_duration >= self.PARAGRAPH_DWELL_SECONDS and not para_triggered:
                    if not self.is_busy():
                        para_triggered = True
                        # Step 1: Check if user already highlighted text (non-destructive)
                        text = self._grab_current_selection_without_clicking()
                        # Step 2: Fallback to triple-click / double-click selection
                        if not text:
                            text = self._grab_selection(cx, cy, mode="paragraph")
                        if text and len(text) >= 3:
                            self.text_detected.emit(text, "paragraph_friction")
            else:
                # Reader scrolled away or jumped to a different section
                para_anchor_y = cy
                para_dwell_start = now
                if y_diff > 130:
                    para_triggered = False

            last_pos = (cx, cy)


# ═══════════════════════════════════════════════════════════════════
#  GUI — DESKTOP PET WIDGET  (FIX #2)
# ═══════════════════════════════════════════════════════════════════

class ScaffyPet(QWidget):
    """Frameless, translucent, always-on-top desktop companion.

    FIX #2: The widget uses *fixed* dimensions (360 × 420) and
    internal margins ≥ 12 px so that child widgets never resolve to
    negative coordinates, which previously caused
    ``UpdateLayeredWindowIndirect failed (The parameter is incorrect)``
    on Windows 11 with translucent backgrounds.
    """

    # ── construction ──────────────────────────────────────────────
    def __init__(self) -> None:
        super().__init__()

        # Window flags: frameless, always on top, no taskbar entry
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # FIX #2: Fixed canvas size — prevents negative-coordinate
        # child widget geometry that triggers the Win32
        # UpdateLayeredWindowIndirect error.
        self.setFixedSize(360, 420)

        # Internal state
        self.old_pos: QPoint | None = None
        self.last_clipboard: str = ""
        self.pet_state: str = "idle"   # idle | thinking | alert | petted
        self.frame: int = 0
        self._worker: BrainWorker | None = None

        # Feature Set 2: Mouse tracking for petting & interactivity
        self.setMouseTracking(True)

        # Audio manager (winsound background queue)
        self._sound_manager = SoundManager()

        # Petting interaction state
        self._petting_points: list[tuple[float, int, int]] = []
        self._last_purr_time: float = 0.0
        self._pet_timer = QTimer(self)
        self._pet_timer.setSingleShot(True)
        self._pet_timer.timeout.connect(self._on_petting_timeout)

        # Mini-animation backflip state & non-repeating encouragement quote deck
        self._flip_frame: int | None = None
        self._tip_deck: list[str] = []
        self._last_tip: str = ""

        self._init_ui()

        # Position at bottom-right corner of the primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 380, screen.height() - 460)

        # Animation timer (~12 FPS for smooth idle bounce)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(80)

        # Clipboard polling timer (600 ms) — Manual Backup Trigger (Ctrl+C)
        self._clip_timer = QTimer(self)
        self._clip_timer.timeout.connect(self._check_clipboard)
        self._clip_timer.start(600)

        # Proactive Windows Sensor (Word Hover Dwell 5s & Paragraph Friction 20s)
        self._sensor_thread = ProactiveSensorThread(
            is_over_scaffy_fn=self.is_over_scaffy,
            is_busy_fn=self.is_busy,
        )
        self._sensor_thread.text_detected.connect(self._on_proactive_detected)
        self._sensor_thread.start()

    def is_over_scaffy(self, x: int, y: int) -> bool:
        """Return True if (x, y) is over Scaffy's window or thought bubble,
        preventing simulated clicks on Scaffy itself."""
        rect = self.geometry()
        margin = 15
        return (
            rect.x() - margin <= x <= rect.x() + rect.width() + margin
            and rect.y() - margin <= y <= rect.y() + rect.height() + margin
        )

    def is_busy(self) -> bool:
        """Return True if Scaffy is currently computing inference."""
        return self.pet_state == "thinking"

    def closeEvent(self, event) -> None:  # noqa: N802
        """Ensure the background sensor thread terminates cleanly on close."""
        if hasattr(self, "_sensor_thread") and self._sensor_thread.isRunning():
            self._sensor_thread.stop()
            self._sensor_thread.wait(400)
        event.accept()

    # ── UI setup ──────────────────────────────────────────────────
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        # FIX #2: Positive internal margins (≥ 12 px on every side)
        # so children never get negative geometry.
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )

        # ── Thought Bubble (hidden until first result) ────────────
        self.bubble = QWidget(self)
        self.bubble.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                border: 1.5px solid #334155;
                border-left: 4px solid #6366F1;
                border-radius: 12px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.bubble.setGraphicsEffect(shadow)

        b_layout = QVBoxLayout(self.bubble)
        # Generous internal padding for the bubble
        b_layout.setContentsMargins(14, 12, 14, 12)
        b_layout.setSpacing(6)

        # Header row: Title + Mute Toggle Button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        # Title (concept name)
        self.b_title = QLabel("✨ Concept")
        self.b_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.b_title.setStyleSheet("color: #818CF8; border: none;")

        # Mute toggle button (🔊 / 🔇)
        self.b_sound_btn = QLabel("🔊")
        self.b_sound_btn.setFont(QFont("Segoe UI", 9))
        self.b_sound_btn.setStyleSheet("""
            QLabel {
                color: #94A3B8;
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 2px 6px;
            }
            QLabel:hover {
                color: #F8FAFC;
                background-color: #334155;
            }
        """)
        self.b_sound_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_sound_btn.setToolTip("Click to Mute / Unmute Audio Feedback")
        self.b_sound_btn.mousePressEvent = lambda _evt: self._toggle_sound()

        header_row.addWidget(self.b_title)
        header_row.addStretch()
        header_row.addWidget(self.b_sound_btn)

        b_layout.addLayout(header_row)

        # Analogy text
        self.b_analogy = QLabel("")
        self.b_analogy.setFont(QFont("Segoe UI", 9))
        self.b_analogy.setStyleSheet("color: #F8FAFC; border: none;")
        self.b_analogy.setWordWrap(True)

        # Example box (hidden when empty)
        self.b_example = QLabel("")
        self.b_example.setFont(QFont("Segoe UI", 8))
        self.b_example.setStyleSheet(
            "background: #1E293B; color: #38BDF8; "
            "padding: 6px 8px; border-radius: 6px; border: none;"
        )
        self.b_example.setWordWrap(True)
        self.b_example.hide()

        # Code box (hidden when empty)
        self.b_code = QLabel("")
        self.b_code.setFont(QFont("Consolas", 8))
        self.b_code.setStyleSheet(
            "background: #020617; color: #4ADE80; "
            "padding: 6px 8px; border-radius: 6px; border: none;"
        )
        self.b_code.setWordWrap(True)
        self.b_code.hide()

        # Dismiss hint
        self.b_hint = QLabel("✕ Click to dismiss")
        self.b_hint.setFont(QFont("Segoe UI", 7))
        self.b_hint.setStyleSheet("color: #64748B; border: none;")
        self.b_hint.setAlignment(Qt.AlignmentFlag.AlignRight)

        b_layout.addWidget(self.b_analogy)
        b_layout.addWidget(self.b_example)
        b_layout.addWidget(self.b_code)
        b_layout.addWidget(self.b_hint)

        # FIX #2: Bubble width leaves room inside the 360-px parent
        # for the 14-px margins on each side (360 − 14 − 14 = 332).
        self.bubble.setFixedWidth(320)
        self.bubble.hide()

        # Click the bubble to dismiss it and return pet to idle
        self.bubble.mousePressEvent = lambda _evt: self._dismiss_bubble()

        layout.addWidget(self.bubble)

    # ── Bubble dismiss (alert → idle transition) ──────────────────
    def _dismiss_bubble(self) -> None:
        """Hide the explanation bubble and return the pet to idle."""
        self.bubble.hide()
        self.pet_state = "idle"

    # ── Audio & Gamification Handlers (Feature Set 2) ─────────────
    def _toggle_sound(self) -> None:
        """Toggle audio feedback on/off."""
        is_muted = self._sound_manager.toggle_mute()
        self.b_sound_btn.setText("🔇" if is_muted else "🔊")

    def _trigger_petting(self) -> None:
        """User is rubbing/petting the mascot! Enter petted state and play soft purr."""
        now = time.time()
        self.pet_state = "petted"
        self._petting_points.clear()

        # Audio feedback: soft purr (throttled to avoid spam)
        if now - self._last_purr_time > 1.2:
            self._last_purr_time = now
            self._sound_manager.play("purr")

        # Revert back to idle/alert after 2.5s of calm
        self._pet_timer.start(2500)

    def _on_petting_timeout(self) -> None:
        """Called when petting motion pauses/stops."""
        if self.pet_state == "petted":
            self.pet_state = "alert" if self.bubble.isVisible() else "idle"

    def _get_next_encouragement_tip(self) -> str:
        """Return a fresh encouragement tip, guaranteeing variety by shuffling
        through the complete quote deck without consecutive repeats."""
        if not self._tip_deck:
            self._tip_deck = list(ENCOURAGEMENT_TIPS)
            random.shuffle(self._tip_deck)
            # Avoid repeating the immediate last tip across shuffles
            if self._last_tip and len(self._tip_deck) > 1 and self._tip_deck[-1] == self._last_tip:
                self._tip_deck[0], self._tip_deck[-1] = self._tip_deck[-1], self._tip_deck[0]
        tip = self._tip_deck.pop()
        self._last_tip = tip
        return tip

    def _trigger_celebration(self) -> None:
        """Trigger celebratory backflip animation, joyful audio, and reading encouragement tip."""
        self._flip_frame = 0  # Starts backflip animation in paintEvent
        self._sound_manager.play("flip")

        # Select a fresh encouragement tip that rotates every time
        tip = self._get_next_encouragement_tip()
        self.b_title.setText("🎉 Scaffy's Spark!")
        self.b_analogy.setText(tip)
        self.b_example.hide()
        self.b_code.hide()
        self.bubble.show()
        self.pet_state = "alert"

    # ── Mouse Interaction & Petting Sensor ────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event) -> None:
        # 1. Window dragging support
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

        # 2. Petting interaction: check if cursor moves rapidly over mascot
        pos = event.position().toPoint()
        # Mascot bounding box around bottom-center (cx=180, by=360)
        mascot_rect = QRect(130, 290, 100, 110)
        if mascot_rect.contains(pos):
            now = time.time()
            self._petting_points.append((now, pos.x(), pos.y()))
            # Keep samples from the last 0.7 seconds
            self._petting_points = [p for p in self._petting_points if now - p[0] <= 0.7]

            if len(self._petting_points) >= 4:
                total_dist = sum(
                    math.hypot(p2[1] - p1[1], p2[2] - p1[2])
                    for p1, p2 in zip(self._petting_points, self._petting_points[1:])
                )
                if total_dist >= 75:  # Rapid stroking / rubbing
                    self._trigger_petting()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        mascot_rect = QRect(130, 290, 100, 110)
        if mascot_rect.contains(pos):
            self._trigger_celebration()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """Right-click menu: Toggle Mute, Reading Spark tip, and Quit."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1.5px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #6366F1;
                color: #FFFFFF;
            }
        """)
        sound_status = "Unmute Audio (🔇)" if self._sound_manager.muted else "Mute Audio (🔊)"
        toggle_sound_act = menu.addAction(sound_status)
        toggle_sound_act.triggered.connect(self._toggle_sound)

        spark_act = menu.addAction("✨ Reading Encouragement Tip (Double-Click)")
        spark_act.triggered.connect(self._trigger_celebration)

        menu.addSeparator()
        quit_act = menu.addAction("✕ Quit Scaffy")
        quit_act.triggered.connect(QApplication.instance().quit)

        menu.exec(event.globalPos())

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None

    # ── Animation tick ────────────────────────────────────────────
    def _tick_animation(self) -> None:
        # 60-frame cycle gives smoother sin-wave based animations
        self.frame = (self.frame + 1) % 60
        if self._flip_frame is not None:
            self._flip_frame += 1
            if self._flip_frame > 20:
                self._flip_frame = None
        self.update()

    # ── Custom painting (mascot with emotional states & backflip) ─
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Mascot anchor: horizontally centred, near the widget bottom
        cx = 180        # center X
        by = 360        # base Y

        # ── Mini-Animation: Celebratory Backflip ──────────────────
        if self._flip_frame is not None:
            progress = min(1.0, self._flip_frame / 20.0)
            jump_y = -int(36.0 * math.sin(math.pi * progress))
            flip_angle = progress * 360.0
        else:
            jump_y = 0
            flip_angle = 0.0

        # ── Per-state bounce / breathing ─────────────────────────
        if self.pet_state == "idle":
            bounce = int(1.5 * math.sin(2 * math.pi * self.frame / 60)) + jump_y
        elif self.pet_state == "thinking":
            bounce = int(2 * math.sin(2 * math.pi * self.frame / 30)) + jump_y
        elif self.pet_state == "petted":
            # Rapid purring vibration
            bounce = int(1.5 * math.sin(2 * math.pi * self.frame / 4)) + jump_y
        else:  # alert / happy — small excited jitter
            bounce = (1 if self.frame % 8 in (2, 3, 4) else 0) + jump_y

        body_col = QColor("#6366F1")
        face_col = QColor("#1E1B4B")
        ear_inner_col = QColor("#A5B4FC")

        # ── Mascot Transform (rotation for backflip) ──────────────
        p.save()
        if self._flip_frame is not None:
            rot_cy = by - 12 + jump_y
            p.translate(cx, rot_cy)
            p.rotate(flip_angle)
            p.translate(-cx, -rot_cy)

        # ── Ears (shape changes with state) ──────────────────────
        p.setBrush(QBrush(body_col))
        p.setPen(Qt.PenStyle.NoPen)

        if self.pet_state == "thinking":
            # Ears tilt outward — wider spread, tips angled away
            p.drawPolygon([
                QPoint(cx - 30, by - 18 - bounce),
                QPoint(cx - 22, by - 44 - bounce),
                QPoint(cx -  8, by - 22 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  8, by - 22 - bounce),
                QPoint(cx + 22, by - 44 - bounce),
                QPoint(cx + 30, by - 18 - bounce),
            ])
            # Inner ear patches (tilted)
            p.setBrush(QBrush(ear_inner_col))
            p.drawPolygon([
                QPoint(cx - 27, by - 20 - bounce),
                QPoint(cx - 22, by - 38 - bounce),
                QPoint(cx - 11, by - 23 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx + 11, by - 23 - bounce),
                QPoint(cx + 22, by - 38 - bounce),
                QPoint(cx + 27, by - 20 - bounce),
            ])
        elif self.pet_state == "alert":
            # Ears perked up — taller, closer together
            p.drawPolygon([
                QPoint(cx - 24, by - 22 - bounce),
                QPoint(cx - 14, by - 48 - bounce),
                QPoint(cx -  4, by - 22 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  4, by - 22 - bounce),
                QPoint(cx + 14, by - 48 - bounce),
                QPoint(cx + 24, by - 22 - bounce),
            ])
            # Inner ear patches (perked)
            p.setBrush(QBrush(ear_inner_col))
            p.drawPolygon([
                QPoint(cx - 21, by - 23 - bounce),
                QPoint(cx - 14, by - 42 - bounce),
                QPoint(cx -  7, by - 23 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  7, by - 23 - bounce),
                QPoint(cx + 14, by - 42 - bounce),
                QPoint(cx + 21, by - 23 - bounce),
            ])
        elif self.pet_state == "petted":
            # Happy relaxed ears tilted sideways softly
            p.drawPolygon([
                QPoint(cx - 28, by - 16 - bounce),
                QPoint(cx - 20, by - 38 - bounce),
                QPoint(cx -  8, by - 18 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  8, by - 18 - bounce),
                QPoint(cx + 20, by - 38 - bounce),
                QPoint(cx + 28, by - 16 - bounce),
            ])
            p.setBrush(QBrush(ear_inner_col))
            p.drawPolygon([
                QPoint(cx - 25, by - 18 - bounce),
                QPoint(cx - 20, by - 32 - bounce),
                QPoint(cx - 11, by - 19 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx + 11, by - 19 - bounce),
                QPoint(cx + 20, by - 32 - bounce),
                QPoint(cx + 25, by - 18 - bounce),
            ])
        else:
            # Idle — relaxed default ears
            p.drawPolygon([
                QPoint(cx - 26, by - 20 - bounce),
                QPoint(cx - 16, by - 42 - bounce),
                QPoint(cx -  6, by - 22 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  6, by - 22 - bounce),
                QPoint(cx + 16, by - 42 - bounce),
                QPoint(cx + 26, by - 20 - bounce),
            ])
            # Inner ear patches (relaxed)
            p.setBrush(QBrush(ear_inner_col))
            p.drawPolygon([
                QPoint(cx - 23, by - 21 - bounce),
                QPoint(cx - 16, by - 36 - bounce),
                QPoint(cx -  9, by - 22 - bounce),
            ])
            p.drawPolygon([
                QPoint(cx +  9, by - 22 - bounce),
                QPoint(cx + 16, by - 36 - bounce),
                QPoint(cx + 23, by - 21 - bounce),
            ])

        # ── Body capsule ─────────────────────────────────────────
        p.setBrush(QBrush(body_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(cx - 32, by - 24 - bounce, 64, 52, 22, 22)

        # ── Belly patch ──────────────────────────────────────────
        p.setBrush(QBrush(QColor("#EEF2FF")))
        p.drawRoundedRect(cx - 18, by - bounce, 36, 26, 12, 12)

        # ── Eyes & expressions ───────────────────────────────────
        if self.pet_state == "thinking":
            # Focused horizontal squint lines  — —
            p.setPen(QPen(face_col, 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(cx - 19, by - 9 - bounce, cx - 7, by - 9 - bounce)
            p.drawLine(cx + 7, by - 10 - bounce, cx + 19, by - 8 - bounce)

        elif self.pet_state in ("alert", "petted"):
            # Happy curved arc eyes  ^ ^  using QPainterPath arcs
            p.setPen(QPen(face_col, 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            left_arc = QPainterPath()
            left_arc.moveTo(cx - 19, by - 6 - bounce)
            left_arc.quadTo(cx - 13, by - 16 - bounce, cx - 7, by - 6 - bounce)
            p.drawPath(left_arc)
            right_arc = QPainterPath()
            right_arc.moveTo(cx + 7, by - 6 - bounce)
            right_arc.quadTo(cx + 13, by - 16 - bounce, cx + 19, by - 6 - bounce)
            p.drawPath(right_arc)

        else:  # idle
            # Round eyes with periodic blink (close for 2 frames)
            is_blink = self.frame in (0, 1, 30, 31)
            p.setBrush(QBrush(face_col))
            if is_blink:
                p.setPen(QPen(face_col, 2.5))
                p.drawLine(cx - 18, by - 9 - bounce, cx - 8, by - 9 - bounce)
                p.drawLine(cx +  8, by - 9 - bounce, cx + 18, by - 9 - bounce)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(cx - 17, by - 13 - bounce, 8, 8)
                p.drawEllipse(cx +  9, by - 13 - bounce, 8, 8)
                # Tiny white shine dots
                p.setBrush(QBrush(QColor("#FFFFFF")))
                p.drawEllipse(cx - 15, by - 12 - bounce, 3, 3)
                p.drawEllipse(cx + 11, by - 12 - bounce, 3, 3)

        # ── Cheeks (glow intensity changes with state) ───────────
        if self.pet_state == "petted":
            # Maximum happy intense pink blush when petted
            p.setBrush(QBrush(QColor(244, 114, 182, 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 27, by - 2 - bounce, 8, 6)
            p.drawEllipse(cx + 19, by - 2 - bounce, 8, 6)
        elif self.pet_state == "alert":
            # Brighter, larger pink cheeks when happy
            p.setBrush(QBrush(QColor(244, 114, 182, 230)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 26, by - 2 - bounce, 7, 5)
            p.drawEllipse(cx + 19, by - 2 - bounce, 7, 5)
        else:
            # Subtle default cheeks
            alpha = 160 if self.pet_state == "idle" else 140
            p.setBrush(QBrush(QColor(244, 114, 182, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
        # ── Cute Open Reading Book & Paws (Oriented towards Scaffy's eyes) ──
        book_cover_col = QColor("#3B82F6")   # Royal blue hardcover
        book_page_col  = QColor("#F8FAFC")   # Left page paper
        book_page2_col = QColor("#F1F5F9")   # Right page paper (subtle shading)
        book_spine_col = QColor("#1E3A8A")   # Deep blue spine crease
        book_line_col  = QColor("#CBD5E1")   # Spine crease shadow
        paw_col        = QColor("#A5B4FC")   # Cat paw color

        book_y = by + 2 - bounce

        # 1. Hardcover backing angled open towards Scaffy's face
        cover_path = QPainterPath()
        cover_path.moveTo(cx - 26, book_y - 8)      # Left top
        cover_path.lineTo(cx, book_y)               # Spine top (lower center)
        cover_path.lineTo(cx + 26, book_y - 8)      # Right top
        cover_path.lineTo(cx + 26, book_y + 14)     # Right bottom
        cover_path.lineTo(cx, book_y + 20)          # Spine bottom
        cover_path.lineTo(cx - 26, book_y + 14)     # Left bottom
        cover_path.closeSubpath()

        p.setBrush(QBrush(book_cover_col))
        p.setPen(QPen(book_spine_col, 1))
        p.drawPath(cover_path)

        # 2. Left Page (slopes upward towards Scaffy's eyes)
        left_page = QPainterPath()
        left_page.moveTo(cx - 24, book_y - 7)
        left_page.lineTo(cx - 1, book_y + 1)
        left_page.lineTo(cx - 1, book_y + 18)
        left_page.lineTo(cx - 24, book_y + 12)
        left_page.closeSubpath()
        p.setBrush(QBrush(book_page_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(left_page)

        # 3. Right Page (slopes upward towards Scaffy's eyes)
        right_page = QPainterPath()
        right_page.moveTo(cx + 1, book_y + 1)
        right_page.lineTo(cx + 24, book_y - 7)
        right_page.lineTo(cx + 24, book_y + 12)
        right_page.lineTo(cx + 1, book_y + 18)
        right_page.closeSubpath()
        p.setBrush(QBrush(book_page2_col))
        p.drawPath(right_page)

        # 4. Spine center crease
        p.setPen(QPen(book_line_col, 1.2))
        p.drawLine(cx, book_y + 1, cx, book_y + 19)

        # 5. Faux text lines on open pages (angled to match reading perspective)
        p.setPen(QPen(QColor("#94A3B8"), 1))
        # Left page lines
        p.drawLine(cx - 21, book_y - 3, cx - 5, book_y + 2)
        p.drawLine(cx - 21, book_y + 1, cx - 5, book_y + 6)
        p.drawLine(cx - 21, book_y + 5, cx - 5, book_y + 10)
        p.drawLine(cx - 21, book_y + 9, cx - 5, book_y + 14)
        # Right page lines
        p.drawLine(cx + 5, book_y + 2, cx + 21, book_y - 3)
        p.drawLine(cx + 5, book_y + 6, cx + 21, book_y + 1)
        p.drawLine(cx + 5, book_y + 10, cx + 21, book_y + 5)
        p.drawLine(cx + 5, book_y + 14, cx + 21, book_y + 9)

        # 6. Golden Amber Bookmark Ribbon hanging down from bottom spine
        p.setPen(QPen(QColor("#F59E0B"), 1.5))
        p.drawLine(cx, book_y + 18, cx + 3, book_y + 25)

        # 7. Cute Cat Paws resting on the outer edges of the book
        p.setBrush(QBrush(paw_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - 28, book_y + 3, 9, 8)
        p.drawEllipse(cx + 19, book_y + 3, 9, 8)

        # Restore from mascot backflip transformation
        p.restore()

        # ── Floating indicators above head (drawn upright) ───────
        if self.pet_state == "thinking":
            # Animated bobbing yellow question mark
            bob = int(4 * math.sin(2 * math.pi * self.frame / 15))
            qm_x = cx + 2
            qm_y = by - 54 - bounce + bob
            p.setBrush(QBrush(QColor(245, 158, 11, 60)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(qm_x - 10, qm_y - 14, 22, 22)
            p.setPen(QPen(QColor("#F59E0B"), 2))
            p.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            p.drawText(qm_x - 4, qm_y + 2, "?")

        elif self.pet_state == "alert":
            # Green sparkle (diamond ✦) near the right ear
            sparkle_phase = (self.frame % 20) / 20.0
            sparkle_alpha = int(255 * (0.5 + 0.5 * math.sin(2 * math.pi * sparkle_phase)))
            sparkle_col = QColor(74, 222, 128, sparkle_alpha)
            p.setBrush(QBrush(sparkle_col))
            p.setPen(Qt.PenStyle.NoPen)
            sx = cx + 30
            sy = by - 38 - bounce
            sparkle_path = QPainterPath()
            sparkle_path.moveTo(sx, sy - 5)
            sparkle_path.lineTo(sx + 3, sy)
            sparkle_path.lineTo(sx, sy + 5)
            sparkle_path.lineTo(sx - 3, sy)
            sparkle_path.closeSubpath()
            p.drawPath(sparkle_path)

            # Second smaller sparkle near left ear
            sparkle_alpha2 = int(255 * (0.5 + 0.5 * math.sin(2 * math.pi * sparkle_phase + math.pi)))
            sparkle_col2 = QColor(74, 222, 128, sparkle_alpha2)
            p.setBrush(QBrush(sparkle_col2))
            sx2 = cx - 28
            sy2 = by - 34 - bounce
            sparkle_path2 = QPainterPath()
            sparkle_path2.moveTo(sx2, sy2 - 3)
            sparkle_path2.lineTo(sx2 + 2, sy2)
            sparkle_path2.lineTo(sx2, sy2 + 3)
            sparkle_path2.lineTo(sx2 - 2, sy2)
            sparkle_path2.closeSubpath()
            p.drawPath(sparkle_path2)

        elif self.pet_state == "petted":
            # Floating pink hearts ♥ bobbing with happy purrs
            heart_bob = int(3 * math.sin(2 * math.pi * self.frame / 12))
            p.setPen(QPen(QColor("#F43F5E"), 1))
            p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            p.drawText(cx + 6, by - 48 - bounce + heart_bob, "♥")
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(cx - 16, by - 44 - bounce - heart_bob, "♥")

        # Celebratory jump sparkles
        if self._flip_frame is not None:
            p.setPen(QPen(QColor("#FBBF24"), 1))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.drawText(cx - 36, by - 30 + jump_y, "✨")
            p.drawText(cx + 26, by - 30 + jump_y, "✨")

    # ── Clipboard watcher (Feature 3: Manual Ctrl+C Backup Trigger) ──
    def _check_clipboard(self) -> None:
        """Poll the clipboard every 600 ms as a manual backup trigger (Ctrl+C).
        Ignore noise, terminal output, short strings, and already-processed content."""
        try:
            text = pyperclip.paste().strip()
        except Exception:
            return

        if not text or text == self.last_clipboard:
            return
        if len(text) < 3:
            return
        # Ignore Windows error pastes and PowerShell prompts
        if text.startswith("UpdateLayeredWindow") or text.startswith("PS C:"):
            return

        self.last_clipboard = text

        # FIX #1b: Truncate to MAX_SNIPPET_CHARS before building prompt
        truncated = text[:MAX_SNIPPET_CHARS]
        self._trigger_analysis(truncated, source="manual")

    # ── Proactive Sensor slot (Features 1 & 2) ────────────────────
    def _on_proactive_detected(self, text: str, reason: str) -> None:
        """Slot: Triggered non-blockingly by ProactiveSensorThread
        via Word Hover Dwell (5s) or Reading Friction (20s)."""
        if not text or len(text) < 3:
            return
        if self.pet_state == "thinking":
            return
        if text == self.last_clipboard:
            return

        self.last_clipboard = text
        truncated = text[:MAX_SNIPPET_CHARS]
        self._trigger_analysis(truncated, source=reason)

    # ── Analysis pipeline ─────────────────────────────────────────
    def _trigger_analysis(self, snippet: str, source: str = "manual") -> None:
        """Show the 'thinking' state and launch a BrainWorker thread."""
        self.pet_state = "thinking"
        if source == "selection":
            self.b_title.setText("📖 Reading Breakdown...")
        elif source == "word_hover":
            self.b_title.setText("🧠 Term Breakdown...")
        elif source == "paragraph_friction":
            self.b_title.setText("📖 Paragraph Breakdown...")
        else:
            self.b_title.setText("🧠 Thinking...")

        # Feature Set 2: Audio feedback - low cute chirp when starting inference
        self._sound_manager.play("chirp")

        preview = snippet[:70] + ("..." if len(snippet) > 70 else "")
        self.b_analogy.setText(f'"{preview}"')
        self.b_example.hide()
        self.b_code.hide()
        self.bubble.show()

        # Keep a reference so the QThread isn't garbage-collected
        self._worker = BrainWorker(snippet)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, data: dict) -> None:
        """Slot: update the bubble with the structured explanation."""
        self.pet_state = "alert"
        self.b_title.setText(f"✨ {data.get('concept', 'Breakdown')}")
        self.b_analogy.setText(f"💡 {data.get('analogy', '')}")

        # Feature Set 2: Audio feedback - friendly soft cat trill (mrrp) when explanation is ready
        self._sound_manager.play("mrrp")

        example = data.get("example", "")
        if example:
            self.b_example.setText(f"🎯 Example: {example}")
            self.b_example.show()
        else:
            self.b_example.hide()

        code = data.get("code", "")
        if code:
            self.b_code.setText(code)
            self.b_code.show()
        else:
            self.b_code.hide()

        self.bubble.show()


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = ScaffyPet()
    pet.show()
    print("🐾 Scaffy is live! Copy any technical text to get an explanation.")
    sys.exit(app.exec())