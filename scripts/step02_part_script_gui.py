from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk


if not getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
else:
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))

from cadtocae.part_script import PartScriptOutput, batch_generate_part_scripts  # noqa: E402


SELECTION_LABELS = {
    "完整构件（推荐）": "complete",
}


def _default_output_dir() -> str:
    documents = Path.home() / "Documents"
    if documents.exists():
        return str(documents / "CADtoCAE_Step02_outputs")
    return str(Path.cwd() / "outputs" / "step02_part_scripts")


def _standards_path() -> str | None:
    candidates = [
        PROJECT_ROOT / "config" / "standards.json",
        Path(sys.executable).resolve().parent / "config" / "standards.json",
        Path.cwd() / "config" / "standards.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


class Step02PartScriptApp(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CADtoCAE Step02 Part 自动建模脚本生成")
        self.geometry("900x620")
        self.minsize(760, 500)

        self.workbook_paths: list[Path] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.output_dir = StringVar(value=_default_output_dir())
        self.selection_label = StringVar(value="完整构件（推荐）")
        self.overwrite = BooleanVar(value=False)

        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Step01 Excel").grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(top)
        buttons.grid(row=0, column=1, sticky="ew")
        ttk.Button(buttons, text="添加 Excel", command=self._add_files).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="添加文件夹", command=self._add_folder).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="清空", command=self._clear_files).pack(side="left")

        ttk.Label(top, text="输出目录").grid(row=1, column=0, sticky="w", pady=(10, 0))
        output_line = ttk.Frame(top)
        output_line.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        output_line.columnconfigure(0, weight=1)
        ttk.Entry(output_line, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(output_line, text="选择", command=self._choose_output_dir).grid(row=0, column=1)

        options = ttk.LabelFrame(self, text="导出设置", padding=12)
        options.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="导出模式").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, values=list(SELECTION_LABELS.keys()), textvariable=self.selection_label, state="readonly", width=18).grid(row=0, column=1, sticky="w", padx=(8, 24))
        ttk.Checkbutton(options, text="允许覆盖同名输出目录", variable=self.overwrite).grid(row=0, column=2, sticky="w")

        middle = ttk.PanedWindow(self, orient="vertical")
        middle.grid(row=2, column=0, sticky="nsew", padx=12)

        file_frame = ttk.LabelFrame(middle, text="待处理 Excel")
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)
        self.file_list = Text(file_frame, height=8, wrap="none")
        self.file_list.grid(row=0, column=0, sticky="nsew")
        file_scroll = ttk.Scrollbar(file_frame, orient="vertical", command=self.file_list.yview)
        file_scroll.grid(row=0, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=file_scroll.set, state="disabled")

        log_frame = ttk.LabelFrame(middle, text="处理日志")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = Text(log_frame, height=12, wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set, state="disabled")

        middle.add(file_frame, weight=1)
        middle.add(log_frame, weight=2)

        bottom = ttk.Frame(self, padding=12)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.start_button = ttk.Button(bottom, text="生成 Part 建模脚本", command=self._start)
        self.start_button.grid(row=0, column=1)

    def _add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="选择 Step01 生成的 components Excel",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        self._add_workbook_paths(selected)

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择存放 components Excel 的文件夹")
        if folder:
            self._add_workbook_paths(path for path in sorted(Path(folder).glob("*.xlsx")) if not path.name.startswith("~$"))

    def _add_workbook_paths(self, paths: object) -> None:
        seen = {str(path.resolve()).lower() for path in self.workbook_paths}
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
                continue
            key = str(path.resolve()).lower()
            if key not in seen:
                seen.add(key)
                self.workbook_paths.append(path)
        self._refresh_file_list()

    def _clear_files(self) -> None:
        self.workbook_paths.clear()
        self._refresh_file_list()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择 Part 脚本输出目录")
        if selected:
            self.output_dir.set(selected)

    def _refresh_file_list(self) -> None:
        self.file_list.configure(state="normal")
        self.file_list.delete("1.0", "end")
        for index, path in enumerate(self.workbook_paths, start=1):
            self.file_list.insert("end", "%02d. %s\n" % (index, path))
        self.file_list.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.workbook_paths:
            messagebox.showwarning("缺少 Excel", "请先添加一个或多个 Step01 components Excel。")
            return
        if not self.output_dir.get().strip():
            messagebox.showwarning("缺少输出目录", "请选择 Part 脚本输出目录。")
            return

        self.progress.configure(maximum=len(self.workbook_paths), value=0)
        self.start_button.configure(state="disabled")
        self._append_log("开始处理 %s 个 Excel。" % len(self.workbook_paths))

        self.worker = threading.Thread(target=self._run_batch, daemon=True)
        self.worker.start()

    def _run_batch(self) -> None:
        standards = _standards_path()
        selection = SELECTION_LABELS[self.selection_label.get()]
        outputs: list[PartScriptOutput] = []
        try:
            for index, workbook_path in enumerate(self.workbook_paths, start=1):
                self.events.put(("log", "[%s/%s] %s" % (index, len(self.workbook_paths), workbook_path.name)))
                result = batch_generate_part_scripts(
                    [workbook_path],
                    self.output_dir.get().strip(),
                    selection=selection,
                    standards_path=standards,
                    overwrite=self.overwrite.get(),
                )[0]
                outputs.append(result)
                if result.part_script_path:
                    self.events.put(("log", "  生成 Part 脚本: %s" % result.part_script_path))
                    if result.components_json_path:
                        self.events.put(("log", "  生成 components JSON: %s" % result.components_json_path))
                    else:
                        self.events.put(("log", "  components 数据: 已嵌入 Part 脚本"))
                    self.events.put(("log", "  导出构件数: %s / 完整构件数: %s / 总行数: %s" % (result.exported_count, result.complete_count, result.row_count)))
                    self.events.put(("log", "  调试报告: %s" % result.report_path))
                else:
                    self.events.put(("log", "  未生成 Part 脚本，查看报告: %s" % result.report_path))
                for message in result.messages:
                    self.events.put(("log", "  - %s" % message))
                self.events.put(("progress", index))
            self.events.put(("done", outputs))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "progress":
                self.progress.configure(value=int(payload))
            elif kind == "done":
                outputs = list(payload)  # type: ignore[arg-type]
                ok_count = sum(1 for item in outputs if item.status == "ok")
                self.start_button.configure(state="normal")
                self._append_log("处理完成：成功 %s 个，需复核/失败 %s 个。" % (ok_count, len(outputs) - ok_count))
                messagebox.showinfo("处理完成", "成功生成 %s 个 Part 脚本；%s 个需要查看报告。" % (ok_count, len(outputs) - ok_count))
            elif kind == "error":
                self.start_button.configure(state="normal")
                self._append_log("错误: %s" % payload)
                messagebox.showerror("处理失败", str(payload))
        self.after(100, self._poll_events)


def main() -> None:
    app = Step02PartScriptApp()
    app.mainloop()


if __name__ == "__main__":
    main()
