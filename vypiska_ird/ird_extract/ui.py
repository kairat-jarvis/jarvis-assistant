"""Главное окно приложения — Выписка ИРД (пакетная обработка)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .batch_tab import BatchTab


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Выписка ИРД")
        self.geometry("1200x740")
        self.minsize(900, 600)

        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        BatchTab(self).pack(fill="both", expand=True)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
