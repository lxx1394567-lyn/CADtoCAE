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

from cadtocae.assembly_script import AssemblyScriptOutput, batch_generate_assembly_scripts  # noqa: E402


COORDINATE_WORKBOOK_PATTERN = "*_coordinate_formula_simple_fixed.xlsx"


class Step04AssemblyScriptApp(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CADtoCAE Step04 Assembly 建模脚本生成")
        self.geometry("920x620")
        self.minsize(760, 500)

        self.folder = StringVar(value="")
        self.overwrite = BooleanVar(value=True)
        self.workbook_paths: list[Path] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="坐标表文件夹").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(top, text="选择", command=self._choose_folder).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(top, text="扫描", command=self._scan_folder).grid(row=0, column=3)

        options = ttk.Frame(self, padding=(12, 0, 12, 8))
        options.grid(row=1, column=0, sticky="ew")
        ttk.Checkbutton(options, text="覆盖同名脚本和报告", variable=self.overwrite).pack(side="left")

        middle = ttk.PanedWindow(self, orient="vertical")
        middle.grid(row=2, column=0, sticky="nsew", padx=12)

        file_frame = ttk.LabelFrame(middle, text="待处理坐标表")
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
        self.log = Text(log_frame, height=14, wrap="word")
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
        self.start_button = ttk.Button(bottom, text="生成 Assembly 脚本", command=self._start)
        self.start_button.grid(row=0, column=1)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="选择坐标表所在文件夹")
        if selected:
            self.folder.set(selected)
            self._scan_folder()

    def _scan_folder(self) -> None:
        folder_text = self.folder.get().strip()
        if not folder_text:
            messagebox.showwarning("缺少文件夹", "请先选择坐标表所在文件夹。")
            return
        folder = Path(folder_text)
        if not folder.exists() or not folder.is_dir():
            messagebox.showwarning("文件夹不存在", "请选择有效的文件夹。")
            return

        self.workbook_paths = [
            path
            for path in sorted(folder.glob(COORDINATE_WORKBOOK_PATTERN))
            if path.is_file() and not path.name.startswith("~$")
        ]
        self._refresh_file_list()
        self._append_log("扫描到 %s 个坐标表。" % len(self.workbook_paths))

    def _refresh_file_list(self) -> None:
        self.file_list.configure(state="normal")
        self.file_list.delete("1.0", "end")
        for index, path in enumerate(self.workbook_paths, start=1):
            self.file_list.insert("end", "%02d. %s\n" % (index, path.name))
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
            self._scan_folder()
        if not self.workbook_paths:
            messagebox.showwarning("没有坐标表", "文件夹内没有找到 *_coordinate_formula_simple_fixed.xlsx。")
            return

        self.progress.configure(maximum=len(self.workbook_paths), value=0)
        self.start_button.configure(state="disabled")
        self._append_log("开始处理 %s 个坐标表。" % len(self.workbook_paths))
        self.worker = threading.Thread(target=self._run_batch, daemon=True)
        self.worker.start()

    def _run_batch(self) -> None:
        outputs: list[AssemblyScriptOutput] = []
        try:
            output_dir = Path(self.folder.get().strip())
            for index, workbook_path in enumerate(self.workbook_paths, start=1):
                self.events.put(("log", "[%s/%s] %s" % (index, len(self.workbook_paths), workbook_path.name)))
                result = batch_generate_assembly_scripts(
                    [workbook_path],
                    output_dir,
                    overwrite=self.overwrite.get(),
                )[0]
                outputs.append(result)
                if result.script_paths:
                    self.events.put(("log", "  项目: %s" % result.project_prefix))
                    if result.assembly_json_path:
                        self.events.put(("log", "  Assembly JSON: %s" % Path(result.assembly_json_path).name))
                    else:
                        self.events.put(("log", "  Assembly 数据: 已嵌入 py 脚本"))
                    for script in result.script_paths:
                        self.events.put(("log", "  Abaqus 脚本: %s" % Path(script).name))
                    self.events.put(("log", "  调试报告: %s" % result.report_path))
                else:
                    self.events.put(("log", "  未生成脚本，请查看报告: %s" % Path(result.report_path).name))
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
                review_count = sum(1 for item in outputs if item.status == "needs_review")
                failed_count = sum(1 for item in outputs if item.status == "failed")
                self.start_button.configure(state="normal")
                self._append_log("处理完成：成功 %s 个，需复核 %s 个，失败 %s 个。" % (ok_count, review_count, failed_count))
                messagebox.showinfo("处理完成", "成功 %s 个；需复核 %s 个；失败 %s 个。" % (ok_count, review_count, failed_count))
            elif kind == "error":
                self.start_button.configure(state="normal")
                self._append_log("错误: %s" % payload)
                messagebox.showerror("处理失败", str(payload))
        self.after(100, self._poll_events)


def main() -> None:
    app = Step04AssemblyScriptApp()
    app.mainloop()


if __name__ == "__main__":
    main()
