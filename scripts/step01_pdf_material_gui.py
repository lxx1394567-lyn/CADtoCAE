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
else:
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))

from cadtocae.material_pdf import (  # noqa: E402
    DEFAULT_ANGLE,
    DEFAULT_LAYOUT,
    DEFAULT_SUPPORT_TYPE,
    SUPPORTED_DOCUMENT_SUFFIXES,
    BatchMaterialOutput,
    batch_extract_material_workbooks,
)


SUPPORT_TYPES = ["单桩单立柱", "单桩双立柱", "双桩"]


def _default_output_dir() -> str:
    documents = Path.home() / "Documents"
    if documents.exists():
        return str(documents / "CADtoCAE_Step01_outputs")
    return str(Path.cwd() / "outputs" / "step01_material_excels")


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


class Step01MaterialApp(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CADtoCAE Step01 材料表截图识别")
        self.geometry("900x640")
        self.minsize(760, 520)

        self.input_paths: list[Path] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.output_dir = StringVar(value=_default_output_dir())
        self.support_type = StringVar(value=DEFAULT_SUPPORT_TYPE)
        self.angle = StringVar(value=DEFAULT_ANGLE)
        self.layout = StringVar(value=DEFAULT_LAYOUT)
        self.auto_project = BooleanVar(value=True)
        self.enable_ocr = BooleanVar(value=True)
        self.overwrite = BooleanVar(value=False)

        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="材料表截图").grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(top)
        buttons.grid(row=0, column=1, sticky="ew")
        ttk.Button(buttons, text="添加 PNG/JPG", command=self._add_files).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="添加文件夹", command=self._add_folder).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="清空", command=self._clear_files).pack(side="left")

        ttk.Label(top, text="输出目录").grid(row=1, column=0, sticky="w", pady=(10, 0))
        output_line = ttk.Frame(top)
        output_line.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        output_line.columnconfigure(0, weight=1)
        ttk.Entry(output_line, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(output_line, text="选择", command=self._choose_output_dir).grid(row=0, column=1)

        options = ttk.LabelFrame(self, text="项目命名与识别设置", padding=12)
        options.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        for col in range(6):
            options.columnconfigure(col, weight=1 if col in {1, 3, 5} else 0)

        ttk.Label(options, text="默认支架类型").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, values=SUPPORT_TYPES, textvariable=self.support_type, state="readonly", width=16).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(options, text="默认倾角").grid(row=0, column=2, sticky="w")
        ttk.Entry(options, textvariable=self.angle, width=12).grid(row=0, column=3, sticky="w", padx=(6, 18))
        ttk.Label(options, text="阵列布置").grid(row=0, column=4, sticky="w")
        ttk.Entry(options, textvariable=self.layout, width=16).grid(row=0, column=5, sticky="ew", padx=(6, 0))

        ttk.Checkbutton(options, text="自动从文件名/截图文字识别支架类型和倾角", variable=self.auto_project).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Checkbutton(options, text="启用 OCR（默认使用内置 RapidOCR）", variable=self.enable_ocr).grid(row=1, column=3, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(options, text="允许覆盖同名输出目录", variable=self.overwrite).grid(row=1, column=5, sticky="w", pady=(10, 0))

        middle = ttk.PanedWindow(self, orient="vertical")
        middle.grid(row=2, column=0, sticky="nsew", padx=12)

        file_frame = ttk.LabelFrame(middle, text="待处理材料表截图")
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
        self.start_button = ttk.Button(bottom, text="开始识别并生成 Excel", command=self._start)
        self.start_button.grid(row=0, column=1)

    def _add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="选择材料表截图",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg"),
                ("PNG files", "*.png"),
                ("JPG files", "*.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        self._add_input_paths(selected)

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择存放材料表截图的文件夹")
        if folder:
            self._add_input_paths(
                path
                for path in sorted(Path(folder).glob("*"))
                if path.is_file() and path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
            )

    def _add_input_paths(self, paths: object) -> None:
        seen = {str(path.resolve()).lower() for path in self.input_paths}
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
                continue
            key = str(path.resolve()).lower()
            if key not in seen:
                seen.add(key)
                self.input_paths.append(path)
        self._refresh_file_list()

    def _clear_files(self) -> None:
        self.input_paths.clear()
        self._refresh_file_list()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择 Excel 输出目录")
        if selected:
            self.output_dir.set(selected)

    def _refresh_file_list(self) -> None:
        self.file_list.configure(state="normal")
        self.file_list.delete("1.0", "end")
        for index, path in enumerate(self.input_paths, start=1):
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
        if not self.input_paths:
            messagebox.showwarning("缺少输入", "请先添加一个或多个材料表截图 PNG/JPG。")
            return
        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning("缺少输出目录", "请选择 Excel 输出目录。")
            return
        if not self.angle.get().strip():
            messagebox.showwarning("缺少倾角", "请填写默认光伏板倾角。")
            return

        self.progress.configure(maximum=len(self.input_paths), value=0)
        self.start_button.configure(state="disabled")
        self._append_log("开始处理 %s 个材料表截图。" % len(self.input_paths))

        self.worker = threading.Thread(target=self._run_batch, daemon=True)
        self.worker.start()

    def _run_batch(self) -> None:
        standards = _standards_path()
        outputs: list[BatchMaterialOutput] = []
        try:
            for index, pdf_path in enumerate(self.input_paths, start=1):
                self.events.put(("log", "[%s/%s] %s" % (index, len(self.input_paths), pdf_path.name)))
                result = batch_extract_material_workbooks(
                    [pdf_path],
                    self.output_dir.get().strip(),
                    fallback_support_type=self.support_type.get().strip(),
                    fallback_angle=self.angle.get().strip(),
                    layout=self.layout.get().strip(),
                    standards_path=standards,
                    prefer_detected_project=self.auto_project.get(),
                    enable_ocr=self.enable_ocr.get(),
                    overwrite=self.overwrite.get(),
                )[0]
                outputs.append(result)
                if result.workbook_path:
                    self.events.put(("log", "  生成 Excel: %s" % result.workbook_path))
                else:
                    self.events.put(("log", "  未生成 Excel。"))
                    if result.manual_template_path:
                        self.events.put(("log", "  待补录模板: %s" % result.manual_template_path))
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
                self._append_log("处理完成：成功 %s 个，需复核 %s 个。" % (ok_count, len(outputs) - ok_count))
                messagebox.showinfo("处理完成", "成功生成 %s 个材料表 Excel；%s 个需要补录或检查 OCR。" % (ok_count, len(outputs) - ok_count))
            elif kind == "error":
                self.start_button.configure(state="normal")
                self._append_log("错误: %s" % payload)
                messagebox.showerror("处理失败", str(payload))
        self.after(100, self._poll_events)


def main() -> None:
    app = Step01MaterialApp()
    app.mainloop()


if __name__ == "__main__":
    main()
