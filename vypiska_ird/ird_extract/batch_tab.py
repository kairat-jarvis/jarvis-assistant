"""Вкладка «Пакет ИРД» — загрузка нескольких PDF, классификация, экспорт Выписки."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .batch_exporter import export_batch_docx
from .classifier import SECTION_LABELS, process_document
from .extractor import extract_pdf_text


class BatchTab(ttk.Frame):
    """Встраивается как вкладка в ttk.Notebook основного окна."""

    COLS = ("№", "Файл", "Тип документа", "Раздел", "Уверенность", "Формулировка")
    COL_WIDTHS = (35, 200, 160, 140, 80, 480)

    def __init__(self, master: ttk.Notebook) -> None:
        super().__init__(master)
        self._items: list[dict] = []          # [{source_file, formatted_text, ...}]
        self._pdf_paths: list[Path] = []      # загруженные PDF
        self._processing = False
        self._queue: queue.Queue = queue.Queue()

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self.after(100, self._drain_queue)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")

        ttk.Button(bar, text="📁 Добавить PDF…", command=self._add_files).pack(side="left")
        ttk.Button(bar, text="🗑 Очистить список", command=self._clear).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.btn_process = ttk.Button(bar, text="▶ Обработать всё", command=self._run_batch)
        self.btn_process.pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="📝 Экспорт Выписки DOCX", command=self._export).pack(side="left")
        self.lbl_count = ttk.Label(bar, text="Файлов: 0", foreground="#666")
        self.lbl_count.pack(side="right")

    def _build_table(self) -> None:
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.tree = ttk.Treeview(frame, columns=self.COLS, show="headings", height=18)
        for col, w in zip(self.COLS, self.COL_WIDTHS):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._on_double_click)

        hint = ttk.Label(self, text="Двойной клик по «Формулировка» → редактирование.", foreground="#666")
        hint.pack(anchor="w", padx=10)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom")
        self.status = ttk.Label(bar, text="Готов", anchor="w", padding=(10, 3))
        self.status.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bar, mode="determinate", length=200)
        self.progress.pack(side="right", padx=8, pady=3)

    # ── Действия ─────────────────────────────────────────────────────────

    def _add_files(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите PDF-документ ИРД",
            filetypes=[("PDF", "*.pdf"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        pp = Path(path)
        if pp in self._pdf_paths:
            self.status.configure(text=f"Уже добавлен: {pp.name}")
            return
        self._pdf_paths.append(pp)
        self.tree.insert(
            "", "end",
            iid=str(pp),
            values=(len(self._pdf_paths), pp.name, "—", "—", "—", ""),
        )
        self.lbl_count.configure(text=f"Файлов: {len(self._pdf_paths)}")
        self.status.configure(text=f"Добавлен: {pp.name}  (всего {len(self._pdf_paths)})")

    def _clear(self) -> None:
        self._pdf_paths.clear()
        self._items.clear()
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.progress.configure(value=0)
        self.lbl_count.configure(text="Файлов: 0")
        self.status.configure(text="Список очищен.")

    def _run_batch(self) -> None:
        if not self._pdf_paths:
            messagebox.showwarning("Нет файлов", "Сначала добавьте PDF.")
            return
        if self._processing:
            return
        self._processing = True
        self.btn_process.configure(state="disabled")
        self._items.clear()
        self.progress.configure(value=0, maximum=len(self._pdf_paths))
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def _batch_worker(self) -> None:
        for idx, pdf_path in enumerate(self._pdf_paths, start=1):
            try:
                def prog(pg, total, note, _path=pdf_path):
                    self._queue.put(("status", f"{_path.name}: {note}"))

                text = extract_pdf_text(str(pdf_path), progress=prog)
                record = process_document(text)
                record["source_file"] = str(pdf_path)
                self._queue.put(("result", idx, pdf_path, record))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", idx, pdf_path, str(exc)))
            self._queue.put(("tick",))

        self._queue.put(("done",))

    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status.configure(text=msg[1])
                elif kind == "tick":
                    cur = self.progress["value"]
                    self.progress.configure(value=cur + 1)
                elif kind == "result":
                    _, idx, pdf_path, record = msg
                    self._items.append(record)
                    section_label = SECTION_LABELS.get(record["section"], record["section"])
                    conf_pct = f"{int(record['confidence'] * 100)}%"
                    self.tree.item(
                        str(pdf_path),
                        values=(
                            idx,
                            pdf_path.name,
                            record["doc_type_label"],
                            section_label,
                            conf_pct,
                            record["formatted_text"],
                        ),
                    )
                    # раскрашиваем строку по confidence
                    tag = "ok" if record["confidence"] >= 0.4 else "warn"
                    self.tree.item(str(pdf_path), tags=(tag,))
                elif kind == "error":
                    _, idx, pdf_path, err = msg
                    self.tree.item(
                        str(pdf_path),
                        values=(idx, pdf_path.name, "ОШИБКА", "—", "—", err),
                        tags=("error",),
                    )
                elif kind == "done":
                    self._processing = False
                    self.btn_process.configure(state="normal")
                    self.status.configure(
                        text=f"Готово: обработано {len(self._items)} из {len(self._pdf_paths)} файлов."
                        " Отредактируйте формулировки и экспортируйте."
                    )
        except queue.Empty:
            pass

        self.tree.tag_configure("ok", foreground="#000000")
        self.tree.tag_configure("warn", foreground="#CC6600")
        self.tree.tag_configure("error", foreground="#CC0000")
        self.after(100, self._drain_queue)

    # ── Редактирование формулировки ──────────────────────────────────────

    def _on_double_click(self, event: tk.Event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != f"#{self.COLS.index('Формулировка') + 1}":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        x, y, w, h = self.tree.bbox(row_id, col)
        current = self.tree.set(row_id, "Формулировка")

        entry = ttk.Entry(self.tree)
        entry.insert(0, current)
        entry.select_range(0, "end")
        entry.focus_set()
        entry.place(x=x, y=y, width=w, height=h)

        def commit(_e=None) -> None:
            if not entry.winfo_exists():
                return
            new_val = entry.get()
            self.tree.set(row_id, "Формулировка", new_val)
            # обновить в _items
            for item in self._items:
                if str(item.get("source_file", "")).endswith(row_id.split("/")[-1]) or row_id == item.get("source_file"):
                    item["formatted_text"] = new_val
                    break
            entry.destroy()

        def cancel(_e=None) -> None:
            if entry.winfo_exists():
                entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    # ── Экспорт ──────────────────────────────────────────────────────────

    def _export(self) -> None:
        if not self._items:
            messagebox.showwarning("Нет данных", "Сначала обработайте файлы.")
            return

        # синхронизируем отредактированные формулировки из дерева
        for item in self._items:
            row_id = item.get("source_file", "")
            if self.tree.exists(row_id):
                item["formatted_text"] = self.tree.set(row_id, "Формулировка")

        path = filedialog.asksaveasfilename(
            title="Сохранить Выписку ИРД",
            defaultextension=".docx",
            initialfile="Выписка_ИРД.docx",
            filetypes=[("Word", "*.docx")],
        )
        if not path:
            return

        project = ""  # можно добавить поле ввода названия объекта
        export_batch_docx(self._items, path, project_name=project)
        self.status.configure(text=f"Сохранено: {Path(path).name}")
        messagebox.showinfo("Экспорт", f"Выписка ИРД сохранена:\n{path}")
