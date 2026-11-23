"""Step06-A v0.2 single Project Folder GUI and development CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import sys
import threading
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, messagebox, ttk

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from cadtocae.hole_projects import scan_projects, generate_batch, generate_hole_tables, can_generate, project_details
from cadtocae.step06_release import generate_release_batch as generate_batch
from cadtocae.step06_version import STEP06_VERSION, version_fields


class Step06App(Tk):
    def __init__(self):
        super().__init__()
        self.title("CADtoCAE Step06 "+STEP06_VERSION+" — Hole Setup / Bolt Connectors")
        self.geometry("1380x820")
        self.minsize(1000, 650)
        self.folder = StringVar()
        self.recursive = BooleanVar(value=False)
        self.status = StringVar(value="Select a Project Folder, then Scan Projects.")
        self.scan = None
        self.busy = False
        self.events = queue.Queue()
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Project Folder").grid(row=0, column=0)
        entry = ttk.Entry(top, textvariable=self.folder)
        entry.grid(row=0, column=1, sticky="ew", padx=10)
        select = ttk.Button(top, text="Select Folder", command=self.choose_folder)
        select.grid(row=0, column=2)
        recursive = ttk.Checkbutton(top, text="Include Subfolders (default OFF)", variable=self.recursive)
        recursive.grid(row=1, column=1, sticky="w", pady=8)
        self.inputs = [entry, select, recursive]
        self.scan_button = ttk.Button(top, text="Scan Projects", command=self.start_scan)
        self.scan_button.grid(row=1, column=2)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        columns = ("project", "structure", "input", "hole_table", "capability", "generation", "result")
        self.table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended", height=10)
        for key, label, width in zip(columns, ("Project ID", "Structure", "Input", "Hole Table", "Capability", "Generation", "Result"),
                                     (330, 85, 135, 180, 130, 130, 350)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=75, stretch=False)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.bind("<<TreeviewSelect>>", self.details)
        actions = ttk.Frame(self, padding=12)
        actions.pack(fill="x")
        self.hole_tables = ttk.Button(actions, text="Generate Hole Tables", command=self.start_tables)
        self.hole_tables.pack(side="left", padx=(0,10))
        self.selected = ttk.Button(actions, text="Generate Selected", command=lambda:self.start_generate(True))
        self.selected.pack(side="left")
        self.all_ready = ttk.Button(actions, text="Generate All Ready", command=lambda:self.start_generate(False))
        self.all_ready.pack(side="left", padx=10)
        ttk.Label(actions, textvariable=self.status).pack(side="left")
        logs = ttk.LabelFrame(self, text="Detail / Log", padding=5)
        logs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = Text(logs, height=13, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(logs, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self.folder.trace_add("write", self.invalidate)
        self.recursive.trace_add("write", self.invalidate)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.buttons()
        self.after(100, self.poll)

    def choose_folder(self):
        value = filedialog.askdirectory(parent=self, title="Select Project Folder")
        if value:
            self.folder.set(value)

    def invalidate(self, *_):
        self.scan = None
        self.table.delete(*self.table.get_children())
        self.status.set("Folder settings changed. Scan Projects to refresh.")
        self.buttons()

    def buttons(self):
        available = self.scan is not None and not self.busy
        self.hole_tables.configure(state="normal" if available and self.scan['projects'] else "disabled")
        ready = bool(available and any(can_generate(r) for r in self.scan["projects"]))
        selected = bool(available and any(can_generate(self.scan["projects"][int(i)]) for i in self.table.selection()))
        self.selected.configure(state="normal" if selected else "disabled")
        self.all_ready.configure(state="normal" if ready else "disabled")
        self.scan_button.configure(state="disabled" if self.busy else "normal")
        for widget in self.inputs:
            widget.configure(state="disabled" if self.busy else "normal")

    @staticmethod
    def row_values(row):
        return (row["project_id"], row["structure_type"] or "UNKNOWN", row["input_status"],
                "; ".join(Path(p).name for p in row["hole_tables"]), row["capability"],
                row["generation_status"], row["result"])

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self, operation):
        self.busy = True
        self.buttons()
        def worker():
            try:
                self.events.put(("done", operation()))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def start_scan(self):
        if self.busy:
            return
        folder, recursive = self.folder.get(), self.recursive.get()
        if not folder:
            messagebox.showerror("Project Folder required", "Select a project folder.", parent=self)
            return
        self.scan = None
        self.table.delete(*self.table.get_children())
        self.status.set("Scanning projects...")
        self.run(lambda:scan_projects(folder, recursive))

    def start_generate(self, selected):
        if self.busy or not self.scan:
            return
        chosen = {(self.scan["projects"][int(i)]["source_folder"], self.scan["projects"][int(i)]["project_id"])
                  for i in self.table.selection()} if selected else None
        if selected and not chosen:
            return
        scan = self.scan
        self.status.set("Generating Step06 hole / connector scripts...")
        self.run(lambda:generate_batch(scan, chosen, lambda event:self.events.put(("progress", event))))

    def start_tables(self):
        if self.busy or not self.scan:
            return
        scan=self.scan
        self.status.set("Generating project hole tables; existing workbooks will be preserved...")
        self.run(lambda:generate_hole_tables(scan, lambda event:self.events.put(("progress",event))))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.append_log(value["row"]["project_id"]+": "+(value["row"]["result"] or value["event"]))
                elif kind == "error":
                    self.busy = False
                    self.status.set("Failed. See Detail / Log.")
                    self.append_log(value)
                else:
                    self.busy = False
                    self.scan = value
                    self.table.delete(*self.table.get_children())
                    for index, row in enumerate(value["projects"]):
                        self.table.insert("", "end", iid=str(index), values=self.row_values(row))
                        self.append_log(project_details(row))
                    counts = value.get("generation_counts")
                    if value.get('table_counts'):
                        self.status.set('Tables created: %(created)d   Preserved: %(preserved)d   Failed: %(failed)d. Fill Excel, then Scan Projects.' % value['table_counts'])
                    elif counts:
                        self.status.set("Generated: %(succeeded)d   Failed: %(failed)d   Skipped: %(skipped)d" % counts)
                    else:
                        self.status.set("%d projects. READY / HOLE_READY means script generation is available; inspect warnings before CAE execution." % len(value["projects"]))
                self.buttons()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def details(self, *_):
        if self.scan and self.table.selection():
            self.append_log(project_details(self.scan["projects"][int(self.table.selection()[0])]))
        self.buttons()

    def close(self):
        if self.busy:
            messagebox.showinfo("Step06", "Wait for the current operation to finish.", parent=self)
            return
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", metavar="PROJECT_FOLDER")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--generate-tables", action="store_true", help="Create missing per-project hole workbooks; never overwrite")
    parser.add_argument("--include-subfolders", action="store_true")
    parser.add_argument("--report", type=Path, help="Development CLI scan/batch report")
    parser.add_argument("--ui-smoke", action="store_true")
    parser.add_argument("--smoke-folder", type=Path, help="Isolated test folder for UI callback smoke test")
    args = parser.parse_args()
    if args.scan:
        result = scan_projects(args.scan, args.include_subfolders)
        result.update(version_fields())
        if args.generate_tables:
            result = generate_hole_tables(result)
        if args.generate:
            result = generate_batch(result)
        result.update(version_fields())
        content = json.dumps(result, ensure_ascii=False, indent=2)
        if args.report:
            args.report.write_text(content, encoding="utf-8")
        if sys.stdout:
            print(content)
        if args.generate and result["generation_counts"]["failed"]:
            return 1
        if args.generate_tables and result.get('table_counts',{}).get('failed'):
            return 1
        return 0
    app = Step06App()
    if args.ui_smoke:
        if args.smoke_folder:
            try:
                app.update()
                buttons={}
                def collect(widget):
                    for child in widget.winfo_children():
                        if isinstance(child,ttk.Button):buttons[str(child['text'])]=child
                        collect(child)
                collect(app)
                required=['Select Folder','Scan Projects','Generate Hole Tables','Generate Selected','Generate All Ready']
                assert all(name in buttons and buttons[name].winfo_ismapped() for name in required)
                filedialog.askdirectory=lambda **kw:str(args.smoke_folder)
                app.run=lambda operation:app.events.put(('done',operation()))
                buttons['Select Folder'].invoke()
                buttons['Scan Projects'].invoke();app.poll()
                assert app.scan and app.scan['projects']
                buttons['Generate Hole Tables'].invoke();app.poll()
                assert not app.scan['table_counts']['failed']
                ready=[str(i) for i,r in enumerate(app.scan['projects']) if can_generate(r)]
                assert ready
                app.table.selection_set(ready);app.buttons()
                buttons['Generate Selected'].invoke();app.poll()
                assert app.scan['generation_counts']['succeeded'] and not app.scan['generation_counts']['failed']
                buttons['Generate All Ready'].invoke();app.poll()
                assert app.scan['generation_counts']['succeeded'] and not app.scan['generation_counts']['failed']
                result=dict(status='SUCCESS',title=app.title(),buttons=required,scan=app.scan,**version_fields())
                if args.report:args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc:
                if args.report:args.report.write_text(json.dumps(dict(status='FAILED',error=str(exc))),encoding='utf-8')
                app.destroy();raise
            app.destroy();return 0
        app.withdraw();app.after(300, app.destroy)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
