from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from tkinter import StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk

if not getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
else:
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))

from cadtocae.assembly_script import AssemblyScriptOutput, generate_assembly_scripts_from_workbook  # noqa: E402


class Step04AssemblyScriptApp(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CADtoCAE Step04 Assembly 建模脚本生成")
        self.geometry("960x650")
        self.minsize(800, 540)
        self.coordinate_path = StringVar(value="")
        self.part_script_path = StringVar(value="")
        self.output_folder = StringVar(value="")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        inputs = ttk.LabelFrame(self, text="Step04 输入", padding=12)
        inputs.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        inputs.columnconfigure(1, weight=1)
        rows = (
            ("Step02 Part Script", self.part_script_path, self._choose_part_script),
            ("Coordinate Excel", self.coordinate_path, self._choose_coordinate),
            ("输出目录", self.output_folder, self._choose_output_folder),
        )
        for row, (label, variable, command) in enumerate(rows):
            ttk.Label(inputs, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(inputs, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            ttk.Button(inputs, text="选择", command=command).grid(row=row, column=2, pady=4)

        log_frame = ttk.LabelFrame(self, text="处理日志")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = Text(log_frame, wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set, state="disabled")

        bottom = ttk.Frame(self, padding=12)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.start_button = ttk.Button(bottom, text="生成 Assembly 脚本", command=self._start)
        self.start_button.grid(row=0, column=1)

    def _choose_part_script(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 Step02 Part Script",
            filetypes=(("Step02 Python", "*_create_parts_in_cae.py"), ("Python", "*.py")),
        )
        if selected:
            self.part_script_path.set(selected)
            if not self.output_folder.get().strip():
                self.output_folder.set(str(Path(selected).parent))

    def _choose_coordinate(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 Coordinate Excel",
            filetypes=(("Coordinate Excel", "*_coordinate*.xlsx"), ("Excel", "*.xlsx")),
        )
        if selected:
            self.coordinate_path.set(selected)
            if not self.output_folder.get().strip():
                self.output_folder.set(str(Path(selected).parent))

    def _choose_output_folder(self) -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            self.output_folder.set(selected)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _validated_paths(self) -> tuple[Path, Path, Path] | None:
        coordinate = Path(self.coordinate_path.get().strip())
        part_script = Path(self.part_script_path.get().strip())
        output = Path(self.output_folder.get().strip())
        if not coordinate.is_file():
            messagebox.showwarning("缺少 Coordinate Excel", "请选择有效的 *_coordinate.xlsx。")
            return None
        if not part_script.is_file():
            messagebox.showwarning("缺少 Step02 Script", "请选择有效的 *_create_parts_in_cae.py。")
            return None
        if not output.exists() or not output.is_dir():
            messagebox.showwarning("输出目录无效", "请选择已经存在的输出目录。")
            return None
        return coordinate, part_script, output

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        paths = self._validated_paths()
        if paths is None:
            return
        self.start_button.configure(state="disabled")
        self.progress.start(12)
        self._append_log("开始 Step04 preflight 和 Assembly Script 生成。")
        self.worker = threading.Thread(target=self._run, args=paths, daemon=True)
        self.worker.start()

    def _run(self, coordinate: Path, part_script: Path, output: Path) -> None:
        try:
            result = generate_assembly_scripts_from_workbook(
                coordinate,
                output,
                components_json=part_script,
                overwrite=True,
            )
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _show_result(self, result: AssemblyScriptOutput) -> None:
        self._append_log("project_id: %s" % result.project_prefix)
        self._append_log("status: %s" % result.status)
        for script in result.script_paths:
            self._append_log("Abaqus Script: %s" % script)
        if result.summary_path:
            self._append_log("Assembly Summary: %s" % result.summary_path)
        self._append_log("Debug Report: %s" % result.report_path)
        for message in result.messages:
            self._append_log(message)
        if result.status == "failed":
            messagebox.showerror("生成失败", "Preflight 未通过，请查看日志和调试报告。")
        else:
            messagebox.showinfo("生成完成", "Assembly Script 已生成，请在 Abaqus/CAE 中人工验证。")

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                self.progress.stop()
                self.start_button.configure(state="normal")
                self._show_result(payload)  # type: ignore[arg-type]
            elif kind == "error":
                self.progress.stop()
                self.start_button.configure(state="normal")
                self._append_log("错误: %s" % payload)
                messagebox.showerror("处理失败", str(payload))
        self.after(100, self._poll_events)


def main() -> None:
    app = Step04AssemblyScriptApp()
    app.mainloop()


if __name__ == "__main__":
    main()
