from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

SPACE_1 = 8
SPACE_2 = 12
SPACE_3 = 16
RADIUS_PAD = 14


def preferred_font_family() -> str:
    if os.name == "nt":
        return "Segoe UI"
    if os.getenv("XDG_CURRENT_DESKTOP"):
        return "Noto Sans"
    if os.uname().sysname == "Darwin":  # pragma: no cover - platform dependent
        return "SF Pro Text"
    return "TkDefaultFont"


class AppScaffold(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, padding: int = 0) -> None:
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.content = ttk.Frame(self._canvas, padding=padding)
        self._window_id = self._canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content_configure, add=True)
        self._canvas.bind("<Configure>", self._on_canvas_configure, add=True)

        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self._canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self._canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def _on_content_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        if event is None:
            return
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_exists():
            return
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
            return
        if event.num == 5:
            self._canvas.yview_scroll(1, "units")
            return
        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        if delta != 0:
            self._canvas.yview_scroll(delta, "units")


class PrimaryButton(ttk.Button):
    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, style="Primary.TButton", **kwargs)


class SecondaryButton(ttk.Button):
    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, style="Secondary.TButton", **kwargs)


class CardFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, style: str = "Card.TFrame", padding: int = SPACE_2) -> None:
        super().__init__(parent, style=style, padding=padding)
        self.grid_columnconfigure(0, weight=1)


class PlaceholderEntry(ttk.Entry):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        placeholder: str,
        style: str = "Search.TEntry",
        **kwargs,
    ) -> None:
        super().__init__(parent, textvariable=textvariable, style=style, **kwargs)
        self._text_var = textvariable
        self._placeholder = placeholder
        self._placeholder_active = False
        self.bind("<FocusIn>", self._clear_placeholder, add=True)
        self.bind("<FocusOut>", self._show_placeholder_if_empty, add=True)
        self.bind("<KeyRelease>", self._sync_state, add=True)
        self._show_placeholder_if_empty()

    def set_placeholder(self, placeholder: str) -> None:
        self._placeholder = placeholder
        if self._placeholder_active:
            self._text_var.set(self._placeholder)

    def get_value(self) -> str:
        if self._placeholder_active or self._text_var.get() == self._placeholder:
            return ""
        return self._text_var.get()

    def _sync_state(self, _event=None) -> None:
        self._placeholder_active = self._text_var.get() == self._placeholder

    def _clear_placeholder(self, _event=None) -> None:
        if self._placeholder_active:
            self._text_var.set("")
            self.configure(style="Search.TEntry")
            self._placeholder_active = False

    def _show_placeholder_if_empty(self, _event=None) -> None:
        if self._text_var.get().strip():
            self.configure(style="Search.TEntry")
            self._placeholder_active = False
            return
        self._text_var.set(self._placeholder)
        self.configure(style="Placeholder.TEntry")
        self._placeholder_active = True


class LoadingState(ttk.Frame):
    def __init__(self, parent: tk.Misc, message: str = "Loading...") -> None:
        super().__init__(parent, style="Card.TFrame", padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=0, column=0, pady=(12, 6), sticky="ew")
        ttk.Label(self, text=message).grid(row=1, column=0, sticky="w")
        self.progress.start(12)


class SkeletonList(ttk.Frame):
    def __init__(self, parent: tk.Misc, rows: int = 6) -> None:
        super().__init__(parent, style="Card.TFrame", padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)
        for idx in range(rows):
            ttk.Label(self, text=("\N{MEDIUM SHADE}" * 36)).grid(row=idx, column=0, sticky="w", pady=2)


class EmptyState(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, message: str) -> None:
        super().__init__(parent, style="Card.TFrame", padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)
        ttk.Label(self, text=title, style="StateTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=message, style="Subtle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))


class ErrorState(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, message: str, action_text: str, on_action) -> None:
        super().__init__(parent, style="Card.TFrame", padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)
        ttk.Label(self, text=title, style="StateErrorTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=message, wraplength=680).grid(row=1, column=0, sticky="w", pady=(4, 6))
        PrimaryButton(self, text=action_text, command=on_action).grid(row=2, column=0, sticky="w")


class FormField(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        label: str,
        textvariable: tk.StringVar,
        width: int = 40,
        placeholder: str | None = None,
    ) -> None:
        super().__init__(parent, style="Card.TFrame", padding=SPACE_2)
        self.grid_columnconfigure(0, weight=1)
        self.label_widget = ttk.Label(self, text=label, style="FieldLabel.TLabel")
        self.label_widget.grid(row=0, column=0, sticky="w")
        if placeholder:
            self.entry = PlaceholderEntry(
                self,
                textvariable=textvariable,
                placeholder=placeholder,
                width=width,
                style="Search.TEntry",
            )
        else:
            self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.error_var = tk.StringVar(value="")
        self.error_label = ttk.Label(self, textvariable=self.error_var, style="FieldError.TLabel")
        self.error_label.grid(row=2, column=0, sticky="w", pady=(2, 0))

    def set_error(self, message: str) -> None:
        self.error_var.set(message)

    def set_label(self, label: str) -> None:
        self.label_widget.configure(text=label)

    def set_placeholder(self, text: str) -> None:
        if isinstance(self.entry, PlaceholderEntry):
            self.entry.set_placeholder(text)

    def get_value(self) -> str:
        if isinstance(self.entry, PlaceholderEntry):
            return self.entry.get_value()
        return self.entry.get()


class ToastManager:
    def __init__(self, root: tk.Tk, reduced_motion: bool = False) -> None:
        self.root = root
        self.reduced_motion = reduced_motion
        self._frame: ttk.Frame | None = None
        self._label: ttk.Label | None = None
        self._action_btn: ttk.Button | None = None
        self._action_callback = None
        self._hide_after: str | None = None

    def show(
        self,
        message: str,
        duration_ms: int = 2600,
        *,
        action_text: str | None = None,
        action_callback=None,
    ) -> None:
        if self._frame is None:
            self._frame = ttk.Frame(self.root, style="ToastFrame.TFrame")
            self._frame.place(relx=0.5, rely=1.0, anchor="s", y=-14)
            self._label = ttk.Label(self._frame, style="Toast.TLabel")
            self._label.grid(row=0, column=0, padx=(0, 8))
            self._action_btn = ttk.Button(self._frame, style="ToastAction.TButton", command=self._handle_action)
            self._frame.grid_columnconfigure(0, weight=1)
        if self._label is None or self._action_btn is None:
            return
        self._label.configure(text=message)
        self._action_callback = action_callback
        if action_text and action_callback:
            self._action_btn.configure(text=action_text)
            self._action_btn.grid(row=0, column=1)
        else:
            self._action_btn.grid_remove()
        if self._hide_after:
            self.root.after_cancel(self._hide_after)
        delay = duration_ms if not self.reduced_motion else min(duration_ms, 1500)
        self._hide_after = self.root.after(delay, self._hide)

    def _handle_action(self) -> None:
        if self._action_callback is not None:
            callback = self._action_callback
            self._action_callback = None
            callback()
        self._hide()

    def _hide(self) -> None:
        if self._frame is not None:
            self._frame.place_forget()
        self._hide_after = None
        self._action_callback = None


class _Tooltip:
    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add=True)
        widget.bind("<Leave>", self._hide, add=True)

    def _show(self, _event=None) -> None:
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.tip, text=self.text, style="Tooltip.TLabel").pack()

    def _hide(self, _event=None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def set_accessibility_label(widget: tk.Misc, label: str) -> None:
    widget.fonte_accessibility_label = label  # type: ignore[attr-defined]
    _Tooltip(widget, label)
