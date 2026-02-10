"""
popup.py — Always-on-top tkinter overlay for the NG negotiation coach.

Provides a frameless, draggable, dark-themed popup that displays real-time
coaching suggestions. Designed to be driven from another thread via the
thread-safe `update_suggestions()` method.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional


# ── Colour palette ──────────────────────────────────────────────────────────
_BG = "#1a1a2e"
_BG_ACCENT = "#16213e"
_TEXT = "#e0e0e0"
_TEXT_DIM = "#8a8a9a"
_BTN_BG = "#0f3460"
_BTN_BG_HOVER = "#1a4a7a"
_WARNING = "#f0a500"
_GREEN = "#2ecc71"
_RED = "#e74c3c"
_SEPARATOR = "#2a2a4e"
_COPIED_BG = "#2ecc71"


class CoachPopup:
    """Frameless always-on-top coaching overlay."""

    # ── construction ────────────────────────────────────────────────────────

    def __init__(self, profile_name: str = ""):
        self.root = tk.Tk()
        self._profile_name = profile_name
        self._on_quit: Optional[Callable] = None
        self._is_active: bool = True

        # Suggestion data (kept for reference / re-draws)
        self._alternatives: Dict[str, str] = {}

        self._setup_window()
        self._setup_styles()
        self._build_ui()
        self._bind_hotkeys()

    # ── public API ──────────────────────────────────────────────────────────

    def set_on_quit(self, callback: Callable) -> None:
        """Register a callback invoked when the user quits (Cmd+Q / close)."""
        self._on_quit = callback

    def update_suggestions(self, suggestions: dict) -> None:
        """Thread-safe update of every UI section.

        Expected keys (all optional):
            one_liner       : str
            recommended     : str
            alternatives    : dict  {"Collaborative": ..., "Assertive": ..., "Probing": ...}
            next_question   : str
            avoid           : list[str]
            risk            : str
        """
        # Schedule the real work on the Tk main-thread.
        try:
            self.root.after(0, self._do_update, suggestions)
        except tk.TclError:
            pass  # Window already destroyed.

    def set_status(self, active: bool) -> None:
        """Update the ON / OFF indicator (thread-safe)."""
        try:
            self.root.after(0, self._do_set_status, active)
        except tk.TclError:
            pass

    def run(self) -> None:
        """Start the tkinter main-loop (blocks)."""
        self.root.mainloop()

    def destroy(self) -> None:
        """Safely tear down the window."""
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    # ── window setup ────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        root = self.root
        root.title("NG")
        root.overrideredirect(True)
        root.wm_attributes("-topmost", True)
        root.wm_attributes("-alpha", 0.95)
        root.configure(bg=_BG)
        root.resizable(False, False)

        # Geometry — 520x680, top-right corner of the primary screen.
        w, h = 520, 680
        screen_w = root.winfo_screenwidth()
        x = screen_w - w - 24
        y = 40
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Hide from screen sharing / screen recording (macOS).
        self._apply_screen_sharing_protection()

    def _apply_screen_sharing_protection(self) -> None:
        """Make the window invisible to screen sharing and screen recording.

        Uses macOS NSWindow.setSharingType_(NSWindowSharingNone).
        The window appears as a black rectangle to anyone viewing a shared screen.
        Falls back silently on non-macOS or if PyObjC is unavailable.
        """
        try:
            from AppKit import NSApp
            # Must call update so Tk creates the underlying NSWindow first.
            self.root.update_idletasks()
            for ns_window in NSApp.windows():
                ns_window.setSharingType_(0)  # NSWindowSharingNone = 0
            print("[NG] Screen sharing protection: ON")
        except Exception:
            print("[NG] Screen sharing protection: unavailable (PyObjC not installed)")

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(
            "Alt.TButton",
            font=("Helvetica", 13),
            background=_BTN_BG,
            foreground=_TEXT,
            borderwidth=0,
            focuscolor="",
            padding=(10, 6),
        )
        style.map(
            "Alt.TButton",
            background=[("active", _BTN_BG_HOVER), ("!active", _BTN_BG)],
            foreground=[("active", _TEXT), ("!active", _TEXT)],
        )

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self.root

        # Outer container with a thin border illusion via padding.
        container = tk.Frame(root, bg=_BG)
        container.pack(fill="both", expand=True, padx=1, pady=1)

        # 1. Title bar ───────────────────────────────────────────────────────
        title_frame = tk.Frame(container, bg=_BG_ACCENT, height=38)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)

        display_name = f"NG \u2014 {self._profile_name}" if self._profile_name else "NG"
        self._title_label = tk.Label(
            title_frame,
            text=display_name,
            font=("Helvetica", 14, "bold"),
            bg=_BG_ACCENT,
            fg=_TEXT,
            anchor="w",
            padx=10,
        )
        self._title_label.pack(side="left", fill="both", expand=True)

        # Status indicator (canvas circle + label).
        status_frame = tk.Frame(title_frame, bg=_BG_ACCENT)
        status_frame.pack(side="right", padx=(0, 10))

        self._status_canvas = tk.Canvas(
            status_frame, width=10, height=10, bg=_BG_ACCENT, highlightthickness=0
        )
        self._status_canvas.pack(side="left", padx=(0, 4), pady=0)
        self._status_dot = self._status_canvas.create_oval(1, 1, 9, 9, fill=_GREEN, outline="")

        self._status_label = tk.Label(
            status_frame,
            text="ON",
            font=("Helvetica", 11),
            bg=_BG_ACCENT,
            fg=_GREEN,
        )
        self._status_label.pack(side="left")

        # Close button.
        close_btn = tk.Label(
            title_frame,
            text="\u2715",
            font=("Helvetica", 15),
            bg=_BG_ACCENT,
            fg=_TEXT_DIM,
            padx=8,
            cursor="hand2",
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", self._quit)

        # Make the title bar (and its label) draggable.
        self._make_draggable(title_frame)
        self._make_draggable(self._title_label)

        # Separator.
        self._sep(container)

        # Scrollable body ────────────────────────────────────────────────────
        body_canvas = tk.Canvas(container, bg=_BG, highlightthickness=0)
        body_canvas.pack(fill="both", expand=True)

        body = tk.Frame(body_canvas, bg=_BG)
        body_window = body_canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(event):
            body_canvas.configure(scrollregion=body_canvas.bbox("all"))
            body_canvas.itemconfigure(body_window, width=event.width)

        body_canvas.bind("<Configure>", _on_body_configure)

        # Allow mouse-wheel scrolling.
        def _on_mousewheel(event):
            body_canvas.yview_scroll(-1 * (event.delta // 120 or event.delta), "units")

        body_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        pad_x = 12
        pad_y = 6

        # 2. One-liner ───────────────────────────────────────────────────────
        ol_frame = tk.Frame(body, bg=_BG)
        ol_frame.pack(fill="x", padx=pad_x, pady=(pad_y + 2, pad_y))

        tk.Label(
            ol_frame,
            text="\U0001F4AC",
            font=("Helvetica", 16),
            bg=_BG,
            fg=_TEXT,
        ).pack(side="left", anchor="n", padx=(0, 6), pady=2)

        self._one_liner_label = tk.Label(
            ol_frame,
            text="Waiting for suggestions\u2026",
            font=("Helvetica", 16, "bold"),
            bg=_BG,
            fg=_TEXT,
            anchor="w",
            justify="left",
            wraplength=460,
            cursor="hand2",
        )
        self._one_liner_label.pack(side="left", fill="x", expand=True)
        self._one_liner_label.bind("<Button-1>", lambda e: self._copy_to_clipboard(self._one_liner_label.cget("text")))

        self._sep(body)

        # 3. Recommended ─────────────────────────────────────────────────────
        rec_frame = tk.Frame(body, bg=_BG)
        rec_frame.pack(fill="x", padx=pad_x, pady=pad_y)

        tk.Label(
            rec_frame,
            text="Recommended:",
            font=("Helvetica", 14, "bold"),
            bg=_BG,
            fg=_TEXT_DIM,
            anchor="w",
        ).pack(fill="x")

        self._recommended_label = tk.Label(
            rec_frame,
            text="\u2014",
            font=("Helvetica", 16),
            bg=_BG,
            fg=_TEXT,
            anchor="w",
            justify="left",
            wraplength=470,
            cursor="hand2",
        )
        self._recommended_label.pack(fill="x", pady=(2, 0))
        self._recommended_label.bind("<Button-1>", lambda e: self._copy_to_clipboard(self._recommended_label.cget("text")))

        self._sep(body)

        # 4. Alternative buttons ─────────────────────────────────────────────
        alt_header = tk.Label(
            body,
            text="Alternatives:",
            font=("Helvetica", 14, "bold"),
            bg=_BG,
            fg=_TEXT_DIM,
            anchor="w",
            padx=pad_x,
        )
        alt_header.pack(fill="x", pady=(pad_y, 2))

        alt_frame = tk.Frame(body, bg=_BG)
        alt_frame.pack(fill="x", padx=pad_x, pady=(0, pad_y))

        self._alt_buttons: Dict[str, ttk.Button] = {}
        for label in ("Collaborative", "Assertive", "Probing"):
            btn = ttk.Button(
                alt_frame,
                text=label,
                style="Alt.TButton",
                command=lambda l=label: self._on_alt_click(l),
            )
            btn.pack(side="left", expand=True, fill="x", padx=2)
            self._alt_buttons[label] = btn

        self._sep(body)

        # 5. Next question ───────────────────────────────────────────────────
        nq_frame = tk.Frame(body, bg=_BG)
        nq_frame.pack(fill="x", padx=pad_x, pady=pad_y)

        tk.Label(
            nq_frame,
            text="Next Q:",
            font=("Helvetica", 14, "bold"),
            bg=_BG,
            fg=_TEXT_DIM,
            anchor="w",
        ).pack(fill="x")

        self._next_q_label = tk.Label(
            nq_frame,
            text="\u2014",
            font=("Helvetica", 16),
            bg=_BG,
            fg=_TEXT,
            anchor="w",
            justify="left",
            wraplength=470,
            cursor="hand2",
        )
        self._next_q_label.pack(fill="x", pady=(2, 0))
        self._next_q_label.bind("<Button-1>", lambda e: self._copy_to_clipboard(self._next_q_label.cget("text")))

        self._sep(body)

        # 6. Warnings ────────────────────────────────────────────────────────
        warn_frame = tk.Frame(body, bg=_BG)
        warn_frame.pack(fill="x", padx=pad_x, pady=pad_y)

        tk.Label(
            warn_frame,
            text="Warnings:",
            font=("Helvetica", 14, "bold"),
            bg=_BG,
            fg=_WARNING,
            anchor="w",
        ).pack(fill="x")

        self._warnings_label = tk.Label(
            warn_frame,
            text="\u2014",
            font=("Helvetica", 14),
            bg=_BG,
            fg=_WARNING,
            anchor="w",
            justify="left",
            wraplength=470,
        )
        self._warnings_label.pack(fill="x", pady=(2, 0))

        # "Copied!" floating feedback label (hidden by default).
        self._copied_label = tk.Label(
            self.root,
            text="Copied!",
            font=("Helvetica", 13, "bold"),
            bg=_COPIED_BG,
            fg="#ffffff",
            padx=10,
            pady=3,
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    def _sep(self, parent: tk.Widget) -> None:
        """Insert a thin horizontal separator."""
        tk.Frame(parent, bg=_SEPARATOR, height=1).pack(fill="x", padx=8, pady=0)

    # ── dragging ────────────────────────────────────────────────────────────

    def _make_draggable(self, widget: tk.Widget) -> None:
        widget.bind("<Button-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_motion)

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_offset_x = event.x
        self._drag_offset_y = event.y

    def _drag_motion(self, event: tk.Event) -> None:
        x = self.root.winfo_x() + event.x - self._drag_offset_x
        y = self.root.winfo_y() + event.y - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    # ── hotkeys ─────────────────────────────────────────────────────────────

    def _bind_hotkeys(self) -> None:
        self.root.bind("<Command-q>", self._quit)
        self.root.bind("<Command-Q>", self._quit)

    def _quit(self, event=None) -> None:
        if self._on_quit:
            try:
                self._on_quit()
            except Exception:
                pass
        self.destroy()

    # ── clipboard / feedback ────────────────────────────────────────────────

    def _copy_to_clipboard(self, text: str) -> None:
        if not text or text == "\u2014":
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()  # Required on some platforms.
        except tk.TclError:
            return
        self._show_copied_feedback()

    def _show_copied_feedback(self) -> None:
        lbl = self._copied_label
        # Place near the top-centre of the window.
        lbl.place(relx=0.5, rely=0.08, anchor="center")
        lbl.lift()
        # Hide after 600 ms.
        try:
            self.root.after(600, lbl.place_forget)
        except tk.TclError:
            pass

    # ── alternative button click ────────────────────────────────────────────

    def _on_alt_click(self, label: str) -> None:
        text = self._alternatives.get(label, "")
        if text:
            self._copy_to_clipboard(text)

    # ── thread-safe update internals ────────────────────────────────────────

    def _do_update(self, suggestions: dict) -> None:
        one_liner: str = suggestions.get("one_liner", "")
        recommended: str = suggestions.get("recommended", "")
        raw_alternatives = suggestions.get("alternatives", [])
        next_question: str = suggestions.get("next_question", "")
        avoid: List[str] = suggestions.get("avoid", [])
        risk: str = suggestions.get("risk", "")

        if one_liner:
            self._one_liner_label.configure(text=one_liner)
        if recommended:
            self._recommended_label.configure(text=recommended)

        # Convert list-of-dicts format from coach to dict for button lookup.
        if raw_alternatives:
            if isinstance(raw_alternatives, list):
                self._alternatives = {
                    alt.get("label", ""): alt.get("text", "")
                    for alt in raw_alternatives
                    if isinstance(alt, dict)
                }
            elif isinstance(raw_alternatives, dict):
                self._alternatives = raw_alternatives

        if next_question:
            self._next_q_label.configure(text=next_question)

        # Build warnings text.
        warn_lines: List[str] = []
        for item in avoid:
            warn_lines.append(f"\u2717  {item}")
        if risk:
            warn_lines.append(f"\u26A0  {risk}")
        if warn_lines:
            self._warnings_label.configure(text="\n".join(warn_lines))
        elif not avoid and not risk:
            self._warnings_label.configure(text="\u2014")

    def _do_set_status(self, active: bool) -> None:
        self._is_active = active
        colour = _GREEN if active else _RED
        label_text = "ON" if active else "OFF"
        self._status_canvas.itemconfigure(self._status_dot, fill=colour)
        self._status_label.configure(text=label_text, fg=colour)


# ── Quick manual test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    popup = CoachPopup(profile_name="Acme Corp")

    # Simulate an update arriving from another thread after 1.5 s.
    def _demo_update():
        popup.update_suggestions(
            {
                "one_liner": "Anchor high and justify with market data.",
                "recommended": (
                    "Based on comparable transactions in Q3, we believe a "
                    "valuation of 8.5x EBITDA is well-supported."
                ),
                "alternatives": {
                    "Collaborative": "What if we explored a structure that works for both sides?",
                    "Assertive": "Our analysis firmly supports the 8.5x multiple.",
                    "Probing": "Could you walk me through how you arrived at that figure?",
                },
                "next_question": "What are your key concerns about the timeline?",
                "avoid": ["Revealing walk-away price", "Discussing other bids"],
                "risk": "Counterpart may try to re-trade on indemnity terms.",
            }
        )

    popup.root.after(1500, _demo_update)

    # Simulate toggling status after 4 s.
    popup.root.after(4000, lambda: popup.set_status(False))
    popup.root.after(6000, lambda: popup.set_status(True))

    popup.set_on_quit(lambda: print("[demo] on_quit callback fired"))
    popup.run()
