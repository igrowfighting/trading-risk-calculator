"""
Trading Risk Calculator — desktop UI (customtkinter).

Manual prices only. Whole shares. Never exceed max risk $.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

import customtkinter as ctk

from trading_risk_calculator import theme as T
from trading_risk_calculator.sizing import (
    SizingError,
    gap_loss,
    normalize_weights,
    plan_exits,
    size_levels,
    soft_weights_near_stop,
    sort_entries_farthest_to_nearest,
    target_pnl,
    validate_entry_vs_stop,
)
from trading_risk_calculator.storage import ExitPlan, Plan, PlanStore


def _f(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_money(v: float, signed: bool = False) -> str:
    if signed:
        return f"${v:+,.2f}"
    return f"${v:,.2f}"


def _fmt_shares(n: int) -> str:
    return f"{n:,}"


class LevelRow:
    """One scale-in entry row: price + weight %."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        index: int,
        on_change,
        on_remove,
        show_remove: bool,
    ) -> None:
        self.index = index
        self.on_change = on_change
        self.frame = ctk.CTkFrame(parent, fg_color=T.PANEL_ALT, corner_radius=6)
        self.lbl = ctk.CTkLabel(
            self.frame, text=f"L{index + 1}", width=28, font=T.LABEL_FONT, text_color=T.TEXT_DIM
        )
        self.lbl.pack(side="left", padx=(8, 4), pady=6)
        self.price = ctk.CTkEntry(
            self.frame,
            width=100,
            placeholder_text="Entry $",
            fg_color=T.INPUT_BG,
            border_color=T.BORDER,
            text_color=T.TEXT,
        )
        self.price.pack(side="left", padx=4, pady=6)
        self.price.bind("<KeyRelease>", lambda _e: on_change())

        self.pct_var = ctk.DoubleVar(value=0.0)
        self.pct_label = ctk.CTkLabel(
            self.frame, text="0%", width=42, font=T.LABEL_FONT, text_color=T.TEXT
        )
        self.pct_label.pack(side="right", padx=(4, 8))

        self.remove_btn = ctk.CTkButton(
            self.frame,
            text="×",
            width=28,
            height=28,
            fg_color=T.RED_SOFT,
            hover_color=T.RED,
            command=lambda: on_remove(self),
        )
        if show_remove:
            self.remove_btn.pack(side="right", padx=4)

        self.slider = ctk.CTkSlider(
            self.frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=120,
            fg_color=T.BORDER,
            progress_color=T.ACCENT,
            button_color=T.TEXT_DIM,
            command=self._on_slide,
        )
        self.slider.pack(side="right", padx=4, pady=6)
        self._syncing = False

    def _on_slide(self, val: float) -> None:
        if self._syncing:
            return
        self.pct_label.configure(text=f"{int(round(val))}%")
        self.on_change()

    def set_pct(self, pct: float) -> None:
        """Set weight percent 0–100 without recursive change storms."""
        self._syncing = True
        try:
            self.slider.set(pct)
            self.pct_label.configure(text=f"{int(round(pct))}%")
        finally:
            self._syncing = False

    def get_pct(self) -> float:
        return float(self.slider.get())

    def get_price(self) -> Optional[float]:
        return _f(self.price.get())

    def set_price(self, v: Optional[float]) -> None:
        self.price.delete(0, "end")
        if v is not None:
            self.price.insert(0, str(v))

    def pack(self, **kw) -> None:
        self.frame.pack(**kw)

    def destroy(self) -> None:
        self.frame.destroy()


class ExitRow:
    def __init__(self, parent, index: int, on_change, on_remove, show_remove: bool) -> None:
        self.on_change = on_change
        self.frame = ctk.CTkFrame(parent, fg_color=T.PANEL_ALT, corner_radius=6)
        ctk.CTkLabel(
            self.frame, text=f"X{index + 1}", width=28, font=T.LABEL_FONT, text_color=T.TEXT_DIM
        ).pack(side="left", padx=(8, 4), pady=6)
        self.price = ctk.CTkEntry(
            self.frame,
            width=100,
            placeholder_text="Exit $",
            fg_color=T.INPUT_BG,
            border_color=T.BORDER,
            text_color=T.TEXT,
        )
        self.price.pack(side="left", padx=4, pady=6)
        self.price.bind("<KeyRelease>", lambda _e: on_change())

        self.pct_label = ctk.CTkLabel(
            self.frame, text="100%", width=42, font=T.LABEL_FONT, text_color=T.TEXT
        )
        self.pct_label.pack(side="right", padx=(4, 8))
        self.remove_btn = ctk.CTkButton(
            self.frame,
            text="×",
            width=28,
            height=28,
            fg_color=T.RED_SOFT,
            hover_color=T.RED,
            command=lambda: on_remove(self),
        )
        if show_remove:
            self.remove_btn.pack(side="right", padx=4)
        self.slider = ctk.CTkSlider(
            self.frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=120,
            fg_color=T.BORDER,
            progress_color=T.GREEN_SOFT,
            button_color=T.TEXT_DIM,
            command=self._on_slide,
        )
        self.slider.set(100)
        self.slider.pack(side="right", padx=4, pady=6)
        self._syncing = False

    def _on_slide(self, val: float) -> None:
        if self._syncing:
            return
        self.pct_label.configure(text=f"{int(round(val))}%")
        self.on_change()

    def set_pct(self, pct: float) -> None:
        self._syncing = True
        try:
            self.slider.set(pct)
            self.pct_label.configure(text=f"{int(round(pct))}%")
        finally:
            self._syncing = False

    def get_pct(self) -> float:
        return float(self.slider.get())

    def get_price(self) -> Optional[float]:
        return _f(self.price.get())

    def set_price(self, v: Optional[float]) -> None:
        self.price.delete(0, "end")
        if v is not None:
            self.price.insert(0, str(v))

    def pack(self, **kw) -> None:
        self.frame.pack(**kw)

    def destroy(self) -> None:
        self.frame.destroy()


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Trading Risk Calculator")
        self.geometry("1100x780")
        self.minsize(960, 680)
        self.configure(fg_color=T.BG)

        self.store = PlanStore()
        self.level_rows: List[LevelRow] = []
        self.exit_rows: List[ExitRow] = []
        self._weight_lock = False
        self._exit_lock = False
        self._last_result = None

        self._build()
        self._add_level(initial=True)
        self._add_exit(initial=True)
        self._refresh_plan_menu()
        self._recalc()

    # ── layout ──────────────────────────────────────────────
    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text="Trading Risk Calculator",
            font=T.TITLE_FONT,
            text_color=T.TEXT,
        ).pack(side="left", padx=16, pady=12)

        ctk.CTkLabel(header, text="Saved", font=T.LABEL_FONT, text_color=T.TEXT_DIM).pack(
            side="left", padx=(24, 4)
        )
        self.plan_menu = ctk.CTkOptionMenu(
            header,
            values=["(none)"],
            width=120,
            fg_color=T.INPUT_BG,
            button_color=T.BORDER,
            button_hover_color=T.ACCENT,
            command=self._on_load_plan,
        )
        self.plan_menu.pack(side="left", padx=4)

        ctk.CTkButton(
            header,
            text="Save Plan",
            width=90,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            command=self._save_plan,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            header,
            text="Delete",
            width=70,
            fg_color=T.RED_SOFT,
            hover_color=T.RED,
            command=self._delete_plan,
        ).pack(side="left", padx=4)

        body = ctk.CTkFrame(self, fg_color=T.BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        left = ctk.CTkScrollableFrame(body, fg_color=T.BG, width=520)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ctk.CTkFrame(body, fg_color=T.BG, width=480)
        right.pack(side="right", fill="both", expand=True)

        self._build_inputs(left)
        self._build_results(right)

        self.status = ctk.CTkLabel(
            self, text="", font=T.LABEL_FONT, text_color=T.WARN, anchor="w"
        )
        self.status.pack(fill="x", padx=16, pady=(0, 8))

    def _panel(self, parent, title: str) -> ctk.CTkFrame:
        wrap = ctk.CTkFrame(parent, fg_color=T.PANEL, corner_radius=10)
        wrap.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            wrap, text=title, font=T.TITLE_FONT, text_color=T.TEXT, anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 4))
        return wrap

    def _build_inputs(self, parent) -> None:
        # Ticker + side
        top = self._panel(parent, "Position")
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(row, text="Ticker", font=T.LABEL_FONT, text_color=T.TEXT_DIM).grid(
            row=0, column=0, sticky="w"
        )
        self.ticker = ctk.CTkEntry(
            row, width=120, placeholder_text="e.g. AAPL",
            fg_color=T.INPUT_BG, border_color=T.BORDER, text_color=T.TEXT,
        )
        self.ticker.grid(row=1, column=0, padx=(0, 12), pady=4)
        self.ticker.bind("<KeyRelease>", lambda _e: self._recalc())

        ctk.CTkLabel(row, text="Side", font=T.LABEL_FONT, text_color=T.TEXT_DIM).grid(
            row=0, column=1, sticky="w"
        )
        self.side_seg = ctk.CTkSegmentedButton(
            row,
            values=["Long", "Short"],
            command=self._on_side,
            fg_color=T.INPUT_BG,
            selected_color=T.GREEN_SOFT,
            selected_hover_color=T.GREEN,
            unselected_color=T.PANEL_ALT,
            unselected_hover_color=T.BORDER,
            text_color=T.TEXT,
        )
        self.side_seg.set("Long")
        self.side_seg.grid(row=1, column=1, padx=(0, 12), pady=4)

        ctk.CTkLabel(row, text="Stop $", font=T.LABEL_FONT, text_color=T.TEXT_DIM).grid(
            row=0, column=2, sticky="w"
        )
        self.stop = ctk.CTkEntry(
            row, width=100, placeholder_text="Required",
            fg_color=T.INPUT_BG, border_color=T.RED_SOFT, text_color=T.TEXT,
        )
        self.stop.grid(row=1, column=2, padx=(0, 12), pady=4)
        self.stop.bind("<KeyRelease>", lambda _e: self._recalc())

        ctk.CTkLabel(row, text="Max Risk $", font=T.LABEL_FONT, text_color=T.TEXT_DIM).grid(
            row=0, column=3, sticky="w"
        )
        self.max_risk = ctk.CTkEntry(
            row, width=100, placeholder_text="Required",
            fg_color=T.INPUT_BG, border_color=T.BORDER, text_color=T.TEXT,
        )
        self.max_risk.grid(row=1, column=3, padx=(0, 12), pady=4)
        self.max_risk.bind("<KeyRelease>", lambda _e: self._recalc())

        ctk.CTkLabel(row, text="Target $ (opt)", font=T.LABEL_FONT, text_color=T.TEXT_DIM).grid(
            row=0, column=4, sticky="w"
        )
        self.target = ctk.CTkEntry(
            row, width=100, placeholder_text="Optional",
            fg_color=T.INPUT_BG, border_color=T.BORDER, text_color=T.TEXT,
        )
        self.target.grid(row=1, column=4, pady=4)
        self.target.bind("<KeyRelease>", lambda _e: self._recalc())

        # Entries / scale-in
        entries_panel = self._panel(parent, "Entry Levels (scale-in optional)")
        hint = ctk.CTkLabel(
            entries_panel,
            text="Order farthest → nearest to stop. Soft weights default ~20/30/50. Sliders sum to 100%.",
            font=T.LABEL_FONT,
            text_color=T.TEXT_DIM,
            wraplength=480,
            justify="left",
        )
        hint.pack(fill="x", padx=12, pady=(0, 6))

        self.levels_box = ctk.CTkFrame(entries_panel, fg_color="transparent")
        self.levels_box.pack(fill="x", padx=8, pady=4)

        btn_row = ctk.CTkFrame(entries_panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(
            btn_row, text="+ Add Level", width=110, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, command=lambda: self._add_level(),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Reset Soft Weights", width=150, fg_color=T.PANEL_ALT,
            hover_color=T.BORDER, command=self._reset_soft_weights,
        ).pack(side="left")
        self.weight_sum_lbl = ctk.CTkLabel(
            btn_row, text="Weights: 100%", font=T.LABEL_FONT, text_color=T.TEXT_DIM
        )
        self.weight_sum_lbl.pack(side="right")

        # Exits
        exits_panel = self._panel(parent, "Exits (optional)")
        ctk.CTkLabel(
            exits_panel,
            text="Full dump at one price, or partial peels with % sliders.",
            font=T.LABEL_FONT,
            text_color=T.TEXT_DIM,
        ).pack(fill="x", padx=12, pady=(0, 6))
        self.exits_box = ctk.CTkFrame(exits_panel, fg_color="transparent")
        self.exits_box.pack(fill="x", padx=8, pady=4)
        exit_btns = ctk.CTkFrame(exits_panel, fg_color="transparent")
        exit_btns.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(
            exit_btns, text="+ Add Exit Peel", width=130, fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER, command=lambda: self._add_exit(),
        ).pack(side="left")
        self.exit_sum_lbl = ctk.CTkLabel(
            exit_btns, text="Exit %: 100%", font=T.LABEL_FONT, text_color=T.TEXT_DIM
        )
        self.exit_sum_lbl.pack(side="right")

        # Gap preview
        gap_panel = self._panel(parent, "Gap Preview")
        grow = ctk.CTkFrame(gap_panel, fg_color="transparent")
        grow.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(
            grow,
            text="Gap-through price (worse than stop)",
            font=T.LABEL_FONT,
            text_color=T.TEXT_DIM,
        ).pack(anchor="w")
        self.gap_price = ctk.CTkEntry(
            grow, width=140, placeholder_text="e.g. below stop",
            fg_color=T.INPUT_BG, border_color=T.BORDER, text_color=T.TEXT,
        )
        self.gap_price.pack(anchor="w", pady=4)
        self.gap_price.bind("<KeyRelease>", lambda _e: self._recalc())

    def _build_results(self, parent) -> None:
        res = self._panel(parent, "Position Size")
        # Big numbers
        grid = ctk.CTkFrame(res, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=8)

        self.big_shares = ctk.CTkLabel(
            grid, text="—", font=T.BIG_NUM_FONT, text_color=T.TEXT
        )
        self.big_shares.grid(row=0, column=0, sticky="w", padx=(0, 24))
        ctk.CTkLabel(
            grid, text="Total Shares", font=T.LABEL_FONT, text_color=T.TEXT_DIM
        ).grid(row=1, column=0, sticky="w", padx=(0, 24), pady=(0, 12))

        self.big_risk = ctk.CTkLabel(
            grid, text="—", font=T.BIG_NUM_FONT, text_color=T.RED
        )
        self.big_risk.grid(row=0, column=1, sticky="w", padx=(0, 24))
        ctk.CTkLabel(
            grid, text="$ Risk Used", font=T.LABEL_FONT, text_color=T.TEXT_DIM
        ).grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(0, 12))

        self.big_avg = ctk.CTkLabel(
            grid, text="—", font=T.BIG_NUM_FONT, text_color=T.TEXT
        )
        self.big_avg.grid(row=0, column=2, sticky="w")
        ctk.CTkLabel(
            grid, text="Avg Cost", font=T.LABEL_FONT, text_color=T.TEXT_DIM
        ).grid(row=1, column=2, sticky="w", pady=(0, 12))

        self.big_pnl = ctk.CTkLabel(
            res, text="Target P&L: —", font=T.MED_NUM_FONT, text_color=T.TEXT_DIM
        )
        self.big_pnl.pack(anchor="w", padx=12, pady=(0, 8))

        self.side_badge = ctk.CTkLabel(
            res, text="LONG", font=T.MED_NUM_FONT, text_color=T.GREEN
        )
        self.side_badge.pack(anchor="w", padx=12, pady=(0, 12))

        # Per-level breakdown
        lvl = self._panel(parent, "Per-Level Breakdown")
        self.level_detail = ctk.CTkTextbox(
            lvl,
            height=160,
            fg_color=T.INPUT_BG,
            text_color=T.TEXT,
            font=("Consolas", 13),
            border_color=T.BORDER,
            border_width=1,
        )
        self.level_detail.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.level_detail.insert("1.0", "Enter stop + max risk + entry to size.")
        self.level_detail.configure(state="disabled")

        # Exit / gap results
        out = self._panel(parent, "Exit & Gap Results")
        self.exit_detail = ctk.CTkTextbox(
            out,
            height=140,
            fg_color=T.INPUT_BG,
            text_color=T.TEXT,
            font=("Consolas", 13),
            border_color=T.BORDER,
            border_width=1,
        )
        self.exit_detail.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.exit_detail.insert("1.0", "")
        self.exit_detail.configure(state="disabled")

        self.gap_result = ctk.CTkLabel(
            out, text="Gap loss: —", font=T.MED_NUM_FONT, text_color=T.RED
        )
        self.gap_result.pack(anchor="w", padx=12, pady=(0, 12))

    # ── levels / exits ──────────────────────────────────────
    def _add_level(self, initial: bool = False) -> None:
        row = LevelRow(
            self.levels_box,
            index=len(self.level_rows),
            on_change=self._on_weight_change,
            on_remove=self._remove_level,
            show_remove=not initial or len(self.level_rows) > 0,
        )
        row.pack(fill="x", pady=3, padx=4)
        self.level_rows.append(row)
        self._renumber_levels()
        self._reset_soft_weights()
        if not initial:
            self._recalc()

    def _remove_level(self, row: LevelRow) -> None:
        if len(self.level_rows) <= 1:
            self._set_status("Need at least one entry level.", warn=True)
            return
        self.level_rows.remove(row)
        row.destroy()
        self._renumber_levels()
        self._reset_soft_weights()
        self._recalc()

    def _renumber_levels(self) -> None:
        for i, row in enumerate(self.level_rows):
            row.index = i
            row.lbl.configure(text=f"L{i + 1}")
            if len(self.level_rows) > 1:
                if not row.remove_btn.winfo_ismapped():
                    row.remove_btn.pack(side="right", padx=4)

    def _reset_soft_weights(self) -> None:
        n = len(self.level_rows)
        w = soft_weights_near_stop(n)
        self._weight_lock = True
        try:
            for row, wi in zip(self.level_rows, w):
                row.set_pct(wi * 100)
        finally:
            self._weight_lock = False
        self._update_weight_sum_label()

    def _on_weight_change(self) -> None:
        if self._weight_lock:
            return
        # Normalize so sliders effectively sum to 100 while editing
        raw = [r.get_pct() for r in self.level_rows]
        total = sum(raw)
        self._update_weight_sum_label(total)
        self._recalc()

    def _update_weight_sum_label(self, total: Optional[float] = None) -> None:
        if total is None:
            total = sum(r.get_pct() for r in self.level_rows)
        color = T.TEXT_DIM if abs(total - 100) < 0.6 else T.WARN
        self.weight_sum_lbl.configure(text=f"Weights: {total:.0f}%", text_color=color)

    def _add_exit(self, initial: bool = False) -> None:
        row = ExitRow(
            self.exits_box,
            index=len(self.exit_rows),
            on_change=self._on_exit_change,
            on_remove=self._remove_exit,
            show_remove=len(self.exit_rows) > 0,
        )
        row.pack(fill="x", pady=3, padx=4)
        self.exit_rows.append(row)
        if len(self.exit_rows) == 1:
            row.set_pct(100)
        else:
            # redistribute evenly
            even = 100.0 / len(self.exit_rows)
            self._exit_lock = True
            try:
                for r in self.exit_rows:
                    r.set_pct(even)
            finally:
                self._exit_lock = False
        self._update_exit_sum_label()
        if not initial:
            self._recalc()

    def _remove_exit(self, row: ExitRow) -> None:
        if len(self.exit_rows) <= 1:
            # keep one empty exit row
            row.set_price(None)
            row.set_pct(100)
            self._recalc()
            return
        self.exit_rows.remove(row)
        row.destroy()
        self._update_exit_sum_label()
        self._recalc()

    def _on_exit_change(self) -> None:
        if self._exit_lock:
            return
        total = sum(r.get_pct() for r in self.exit_rows)
        self._update_exit_sum_label(total)
        self._recalc()

    def _update_exit_sum_label(self, total: Optional[float] = None) -> None:
        if total is None:
            total = sum(r.get_pct() for r in self.exit_rows)
        color = T.TEXT_DIM if total <= 100.6 else T.WARN
        self.exit_sum_lbl.configure(text=f"Exit %: {total:.0f}%", text_color=color)

    def _on_side(self, _value: str) -> None:
        side = self.side_seg.get()
        if side == "Long":
            self.side_seg.configure(selected_color=T.GREEN_SOFT, selected_hover_color=T.GREEN)
            self.side_badge.configure(text="LONG", text_color=T.GREEN)
        else:
            self.side_seg.configure(selected_color=T.RED_SOFT, selected_hover_color=T.RED)
            self.side_badge.configure(text="SHORT", text_color=T.RED)
        self._recalc()

    # ── calc ────────────────────────────────────────────────
    def _side(self) -> str:
        return self.side_seg.get().lower()

    def _collect_entries(self) -> Tuple[List[float], List[str]]:
        entries: List[float] = []
        errs: List[str] = []
        for i, row in enumerate(self.level_rows):
            p = row.get_price()
            if p is None:
                continue
            if p <= 0:
                errs.append(f"Level {i + 1}: price must be positive")
                continue
            entries.append(p)
        return entries, errs

    def _weights_for(self, n: int) -> List[float]:
        if n == 0:
            return []
        # Use only rows that have prices, in order — map weights from filled rows
        filled = [r for r in self.level_rows if r.get_price() is not None]
        if len(filled) != n:
            # fall back to soft
            return soft_weights_near_stop(n)
        raw = [r.get_pct() for r in filled]
        if sum(raw) <= 0:
            return soft_weights_near_stop(n)
        try:
            return normalize_weights(raw)
        except SizingError:
            return soft_weights_near_stop(n)

    def _recalc(self) -> None:
        self._set_status("")
        stop = _f(self.stop.get())
        max_risk = _f(self.max_risk.get())
        entries, entry_errs = self._collect_entries()
        side = self._side()

        # Clear big numbers until valid
        def clear_results(msg: str = "") -> None:
            self.big_shares.configure(text="—")
            self.big_risk.configure(text="—")
            self.big_avg.configure(text="—")
            self.big_pnl.configure(text="Target P&L: —", text_color=T.TEXT_DIM)
            self._set_textbox(self.level_detail, msg or "Enter stop + max risk + entry to size.")
            self._set_textbox(self.exit_detail, "")
            self.gap_result.configure(text="Gap loss: —", text_color=T.TEXT_DIM)
            self._last_result = None

        if entry_errs:
            clear_results("\n".join(entry_errs))
            self._set_status("; ".join(entry_errs), warn=True)
            return

        if stop is None or max_risk is None or not entries:
            clear_results()
            return

        if stop <= 0 or max_risk < 0:
            clear_results("Stop must be > 0; max risk must be ≥ 0.")
            self._set_status("Stop must be > 0; max risk must be ≥ 0.", warn=True)
            return

        # Validate each entry vs stop
        warnings = []
        for i, e in enumerate(entries):
            msg = validate_entry_vs_stop(side, e, stop)
            if msg:
                warnings.append(f"L{i + 1}: {msg}")
        if warnings:
            clear_results("\n".join(warnings))
            self._set_status("Invalid levels — fix entry vs stop.", warn=True)
            return

        weights = self._weights_for(len(entries))
        try:
            result = size_levels(side, entries, stop, max_risk, weights=weights)
        except SizingError as exc:
            clear_results(str(exc))
            self._set_status(str(exc), warn=True)
            return

        self._last_result = result
        self.big_shares.configure(text=_fmt_shares(result.total_shares))
        self.big_risk.configure(text=_fmt_money(result.total_risk_used), text_color=T.RED)
        self.big_avg.configure(text=_fmt_money(result.avg_cost) if result.total_shares else "—")

        tgt = _f(self.target.get())
        if tgt is not None and result.total_shares > 0:
            pnl = target_pnl(side, result.avg_cost, result.total_shares, tgt)
            color = T.GREEN if pnl >= 0 else T.RED
            self.big_pnl.configure(
                text=f"Target P&L: {_fmt_money(pnl, signed=True)}",
                text_color=color,
            )
        else:
            self.big_pnl.configure(text="Target P&L: —", text_color=T.TEXT_DIM)

        lines = [
            f"{'Lv':<4}{'Entry':>10}{'Wt%':>8}{'Shares':>10}{'R/sh':>10}{'Tranche $':>12}",
            "-" * 56,
        ]
        for i, lv in enumerate(result.levels):
            lines.append(
                f"{i + 1:<4}{lv.entry:>10.4g}{lv.weight * 100:>7.0f}%{lv.shares:>10,}"
                f"{lv.risk_per_share:>10.4g}{lv.tranche_risk:>12.2f}"
            )
        lines.append("-" * 56)
        lines.append(
            f"{'TOT':<4}{result.avg_cost:>10.4g}{'':>8}{result.total_shares:>10,}"
            f"{'':>10}{result.total_risk_used:>12.2f}"
        )
        lines.append(
            f"Risk remaining: {_fmt_money(result.risk_remaining)}  |  Cap: {_fmt_money(result.max_risk)}"
        )
        self._set_textbox(self.level_detail, "\n".join(lines))

        # Exits
        exit_lines: List[str] = []
        exit_prices = []
        exit_pcts = []
        for row in self.exit_rows:
            p = row.get_price()
            if p is None:
                continue
            exit_prices.append(p)
            exit_pcts.append(row.get_pct() / 100.0)

        if exit_prices and result.total_shares > 0:
            try:
                # If single exit with no intentional partial, force 100%
                if len(exit_prices) == 1 and exit_pcts[0] <= 0:
                    exit_pcts = [1.0]
                er = plan_exits(
                    side, result.avg_cost, result.total_shares, exit_prices, exit_pcts
                )
                exit_lines.append(
                    f"{'Exit':<6}{'Price':>10}{'%':>8}{'Shares':>10}{'P&L':>12}"
                )
                exit_lines.append("-" * 48)
                for i, t in enumerate(er.tranches):
                    exit_lines.append(
                        f"{i + 1:<6}{t.price:>10.4g}{t.pct * 100:>7.0f}%"
                        f"{t.shares:>10,}{t.pnl:>12.2f}"
                    )
                exit_lines.append("-" * 48)
                exit_lines.append(
                    f"Total exit P&L: {_fmt_money(er.total_pnl, signed=True)}  "
                    f"| Remaining shares: {er.remaining_shares}"
                )
                color = T.GREEN if er.total_pnl >= 0 else T.RED
                # keep in textbox; color via gap label style not needed
            except SizingError as exc:
                exit_lines.append(f"Exit error: {exc}")
        else:
            exit_lines.append("Optional: set an exit price (full dump) or peels.")

        self._set_textbox(self.exit_detail, "\n".join(exit_lines))

        # Gap
        gp = _f(self.gap_price.get())
        if gp is not None and result.total_shares > 0:
            gl = gap_loss(side, result.avg_cost, result.total_shares, gp)
            self.gap_result.configure(
                text=f"Gap loss estimate: {_fmt_money(gl, signed=True)} @ {gp:g}",
                text_color=T.RED if gl < 0 else T.GREEN,
            )
        else:
            self.gap_result.configure(text="Gap loss: —", text_color=T.TEXT_DIM)

    def _set_textbox(self, box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _set_status(self, msg: str, warn: bool = False) -> None:
        self.status.configure(text=msg, text_color=T.WARN if warn else T.TEXT_DIM)

    # ── plans ───────────────────────────────────────────────
    def _refresh_plan_menu(self, select: Optional[str] = None) -> None:
        tickers = self.store.list_tickers()
        values = ["(none)"] + tickers
        self.plan_menu.configure(values=values)
        if select and select in values:
            self.plan_menu.set(select)
        elif not tickers:
            self.plan_menu.set("(none)")

    def _gather_plan(self) -> Optional[Plan]:
        ticker = self.ticker.get().strip().upper()
        if not ticker:
            self._set_status("Enter a ticker before saving.", warn=True)
            return None
        stop = _f(self.stop.get()) or 0.0
        max_risk = _f(self.max_risk.get()) or 0.0
        entries = []
        weights = []
        for row in self.level_rows:
            p = row.get_price()
            if p is None:
                continue
            entries.append(p)
            weights.append(row.get_pct() / 100.0)
        if weights:
            try:
                weights = normalize_weights(weights)
            except SizingError:
                weights = soft_weights_near_stop(len(entries))

        exit_prices = []
        exit_pcts = []
        for row in self.exit_rows:
            p = row.get_price()
            if p is None:
                continue
            exit_prices.append(p)
            exit_pcts.append(row.get_pct() / 100.0)
        exit_plan = None
        if exit_prices:
            mode = "full" if len(exit_prices) == 1 else "partial"
            exit_plan = ExitPlan(mode=mode, prices=exit_prices, pcts=exit_pcts)

        return Plan(
            ticker=ticker,
            side=self._side(),
            entries=entries,
            stop=stop,
            max_risk=max_risk,
            target=_f(self.target.get()),
            weights=weights or None,
            exit_plan=exit_plan,
            gap_price=_f(self.gap_price.get()),
        )

    def _save_plan(self) -> None:
        plan = self._gather_plan()
        if not plan:
            return
        self.store.upsert(plan)
        self._refresh_plan_menu(select=plan.ticker)
        self._set_status(f"Saved plan for {plan.ticker}.")

    def _delete_plan(self) -> None:
        ticker = self.ticker.get().strip().upper()
        if not ticker:
            cur = self.plan_menu.get()
            if cur and cur != "(none)":
                ticker = cur
        if not ticker or ticker == "(none)":
            self._set_status("No plan selected to delete.", warn=True)
            return
        if self.store.delete(ticker):
            self._refresh_plan_menu()
            self._set_status(f"Deleted plan for {ticker}.")
        else:
            self._set_status(f"No saved plan for {ticker}.", warn=True)

    def _on_load_plan(self, choice: str) -> None:
        if not choice or choice == "(none)":
            return
        plan = self.store.get(choice)
        if not plan:
            return
        self._apply_plan(plan)

    def _apply_plan(self, plan: Plan) -> None:
        self.ticker.delete(0, "end")
        self.ticker.insert(0, plan.ticker)
        self.side_seg.set("Long" if plan.side == "long" else "Short")
        self._on_side(self.side_seg.get())

        self.stop.delete(0, "end")
        if plan.stop:
            self.stop.insert(0, str(plan.stop))
        self.max_risk.delete(0, "end")
        if plan.max_risk:
            self.max_risk.insert(0, str(plan.max_risk))
        self.target.delete(0, "end")
        if plan.target is not None:
            self.target.insert(0, str(plan.target))
        self.gap_price.delete(0, "end")
        if plan.gap_price is not None:
            self.gap_price.insert(0, str(plan.gap_price))

        # Rebuild levels
        for row in list(self.level_rows):
            row.destroy()
        self.level_rows.clear()
        entries = plan.entries or [None]
        for _ in entries:
            self._add_level(initial=True)
        # _add_level resets soft weights each time — set prices then weights
        for row, e in zip(self.level_rows, entries):
            row.set_price(e)
        if plan.weights and len(plan.weights) == len(self.level_rows):
            self._weight_lock = True
            try:
                for row, w in zip(self.level_rows, plan.weights):
                    row.set_pct(w * 100)
            finally:
                self._weight_lock = False
        else:
            self._reset_soft_weights()

        # Exits
        for row in list(self.exit_rows):
            row.destroy()
        self.exit_rows.clear()
        if plan.exit_plan and plan.exit_plan.prices:
            for _ in plan.exit_plan.prices:
                self._add_exit(initial=True)
            for row, p in zip(self.exit_rows, plan.exit_plan.prices):
                row.set_price(p)
            pcts = plan.exit_plan.pcts
            if pcts and len(pcts) == len(self.exit_rows):
                self._exit_lock = True
                try:
                    for row, p in zip(self.exit_rows, pcts):
                        row.set_pct(p * 100)
                finally:
                    self._exit_lock = False
        else:
            self._add_exit(initial=True)

        self._update_weight_sum_label()
        self._update_exit_sum_label()
        self._recalc()
        self._set_status(f"Loaded plan {plan.ticker}.")


def main() -> None:
    # Prefer dark mode; charcoal set via widget colors
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
