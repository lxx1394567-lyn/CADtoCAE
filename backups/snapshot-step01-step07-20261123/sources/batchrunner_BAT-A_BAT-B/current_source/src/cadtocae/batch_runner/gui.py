"""Tkinter UI; all worker updates cross a queue to the UI thread."""
import copy
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .executor import AbaqusExecutor
from .runner import BatchRunner
from .settings import detected_command, save_successful_configuration, load_preferences

class BatchRunnerGUI:
    def __init__(self, root):
        self.root = root
        root.title('CADtoCAE BatchRunner V4.0 — 一键批量建模')
        root.geometry('1440x780')
        self.events = queue.Queue()
        self.runner = None
        self.busy = False
        self.projects = []
        self.selected = set()
        self.report_dir = None
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.command = tk.StringVar(value=(detected_command() or [''])[0])
        self.config = tk.StringVar()
        self.mode = tk.StringVar(value='smart')
        self.start = tk.IntVar(value=4)
        self.through = tk.IntVar(value=9)
        self.continue_errors = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='选择项目目录后自动检查，一键开始将从可靠检查点继续。')
        self.last_records = {}
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='项目根目录').grid(row=0, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.source).grid(row=0, column=1, columnspan=5, sticky='ew', padx=5)
        ttk.Button(frame, text='选择文件夹', command=lambda:self.choose(self.source)).grid(row=0, column=6)
        self.advanced = ttk.LabelFrame(frame, text='高级设置（普通运行无需配置 JSON）', padding=6)
        for index, (label, var, chooser) in enumerate([
            ('输出目录', self.output, lambda:self.choose(self.output)),
            ('Abaqus 启动器', self.command, lambda:self.choose_file(self.command)),
            ('调度器配置 JSON', self.config, lambda:self.choose_file(self.config)),
        ]):
            ttk.Label(self.advanced, text=label).grid(row=index,column=0,sticky='w')
            ttk.Entry(self.advanced,textvariable=var,width=75).grid(row=index,column=1,sticky='ew')
            ttk.Button(self.advanced,text='浏览',command=chooser).grid(row=index,column=2)
        modes=ttk.Frame(self.advanced)
        modes.grid(row=3,column=0,columnspan=3,sticky='w')
        for label,value in [('智能续跑','smart'),('全量','full'),('断点续跑','resume'),('指定步骤','from')]:
            ttk.Radiobutton(modes,text=label,variable=self.mode,value=value).pack(side='left',padx=3)
        ttk.Spinbox(modes,from_=1,to=9,textvariable=self.start,width=3).pack(side='left')
        ttk.Label(modes,text='执行至 Step').pack(side='left')
        ttk.Spinbox(modes,from_=1,to=9,textvariable=self.through,width=3).pack(side='left')
        ttk.Checkbutton(modes,text='失败后继续下一项目',variable=self.continue_errors).pack(side='left',padx=8)
        ttk.Button(modes,text='打开日志与检查点目录',command=self.open_reports).pack(side='left')
        self.advanced.columnconfigure(1,weight=1)
        controls=ttk.Frame(frame)
        controls.grid(row=1,column=0,columnspan=7,sticky='ew',pady=8)
        self.scan_button=ttk.Button(controls,text='扫描 / 刷新',command=self.scan)
        self.scan_button.pack(side='left')
        ttk.Button(controls,text='全选 / 全不选',command=self.toggle_all).pack(side='left',padx=5)
        self.run_button=ttk.Button(controls,text='一键开始',command=self.launch)
        self.run_button.pack(side='left',padx=5)
        ttk.Button(controls,text='安全停止',command=self.stop).pack(side='left',padx=5)
        ttk.Button(controls,text='查看错误详情',command=self.show_errors).pack(side='left',padx=5)
        ttk.Button(controls,text='高级设置',command=self.toggle_advanced).pack(side='right')
        columns = ('selected', 'prefix', 'part', 'assembly', 'analysis', 'hole', 'tie', 'step', 'bc', 'mesh', 'load', 'completion', 'model_path')
        self.table = ttk.Treeview(frame, columns=columns, show='headings', height=9)
        for key, label in zip(columns, ['选择', '项目', 'Part', 'Assembly', 'Analysis', 'Hole', 'Tie', 'Step', 'BC', 'Mesh', 'Load', '建模 / 交付状态', '当前 CAE 路径']):
            self.table.heading(key, text=label)
            self.table.column(key, width=80 if key not in ('prefix', 'completion', 'model_path') else 250, stretch=key in ('prefix','model_path'))
        self.table.tag_configure('missing', foreground='#666666')
        self.table.tag_configure('failed', foreground='#ad2222')
        self.table.grid(row=5, column=0, columnspan=7, sticky='nsew')
        scroll = ttk.Scrollbar(frame, orient='horizontal', command=self.table.xview)
        self.table.configure(xscrollcommand=scroll.set)
        scroll.grid(row=4, column=0, columnspan=7, sticky='ew')
        self.table.bind('<ButtonRelease-1>', self.click)
        self.table.bind('<<TreeviewSelect>>', lambda event: self.show_project(self.table.selection()[0]) if self.table.selection() else None)
        ttk.Label(frame, textvariable=self.status, wraplength=1080).grid(row=6, column=0, columnspan=7, sticky='w', pady=8)
        self.details = ttk.Treeview(frame, columns=('path','check'), show='tree headings', height=8)
        self.details.heading('#0',text='阶段文件详情（展开查看）')
        self.details.heading('path',text='实际路径 / 运行副本')
        self.details.heading('check',text='校验 / 来源')
        self.details.column('#0',width=200)
        self.details.column('path',width=600)
        self.details.column('check',width=210)
        self.details.grid(row=7,column=0,columnspan=7,sticky='nsew')
        self.log = tk.Text(frame, height=6, wrap='word')
        self.log.grid(row=8, column=0, columnspan=7, sticky='nsew')
        ttk.Button(frame, text='打开运行报告与日志目录', command=self.open_reports).grid(row=9, column=0, columnspan=7, sticky='w')
        delivery_controls = ttk.Frame(frame)
        delivery_controls.grid(row=10, column=0, columnspan=7, sticky='w', pady=5)
        ttk.Button(delivery_controls, text='打开 CAE 结果目录', command=self.open_results).pack(side='left', padx=4)
        ttk.Button(delivery_controls, text='打开 CAE（优先完整模型）', command=self.open_final).pack(side='left', padx=4)
        ttk.Button(delivery_controls, text='查看模型交付详情', command=self.show_delivery).pack(side='left', padx=4)
        ttk.Button(delivery_controls, text='历史文件迁移', command=self.migrate_legacy).pack(side='left', padx=4)
        self.delivery_text = tk.StringVar(value='模型交付：尚未验证')
        ttk.Label(frame, textvariable=self.delivery_text, wraplength=1080).grid(row=11, column=0, columnspan=7, sticky='w')
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        frame.rowconfigure(7, weight=1)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def choose(self, var):
        value = filedialog.askdirectory()
        if value:
            var.set(value)
            if var is self.source:
                self.output.set(str(Path(value)/'.batchrunner'))
                self.scan()

    def choose_file(self, var):
        value = filedialog.askopenfilename()
        if value:
            var.set(value)

    def make_runner(self):
        if not self.source.get() or not self.output.get():
            raise ValueError('请选择项目根目录和独立运行输出目录')
        config = json.loads(Path(self.config.get()).read_text(encoding='utf-8-sig')) if self.config.get() else {}
        return BatchRunner(self.source.get(), self.output.get(),
                           AbaqusExecutor(config.get('command', [self.command.get()]), config.get('environment', load_preferences().get('environment', {}))),
                           lambda item: self.events.put(('update', copy.deepcopy(item))), through=self.through.get())

    def scan(self):
        if self.busy:
            return
        try:
            if not self.output.get():
                self.output.set(str(Path(self.source.get())/'.batchrunner'))
            self.runner = self.make_runner()
            self.projects = self.runner.inspect()
            self.last_records = {}
            for project in self.projects:
                try:
                    record = json.loads((self.runner.output/'history'/(project.key+'-latest.json')).read_text(encoding='utf-8'))
                    self.last_records[project.key] = record
                except (OSError, ValueError):
                    pass
            self.selected = {p.key for p in self.projects}
            self.table.delete(*self.table.get_children())
            for p in self.projects:
                self.table.insert('', 'end', iid=p.key, values=['☑', p.prefix]+[self.stage_label(s) for s in p.stages], tags=('missing',) if any(s.status == 'MISSING' for s in p.stages) else ())
            for project in self.projects:
                self.refresh_delivery_row(project.key)
            if self.projects:
                self.table.selection_set(self.projects[0].key)
                self.show_project(self.projects[0].key)
            self.status.set('识别 %d 个项目；单击选择列勾选，单击项目查看依赖和路径风险。' % len(self.projects))
        except Exception as exc:
            messagebox.showerror('扫描失败', str(exc))

    def click(self, event):
        key = self.table.identify_row(event.y)
        if not key:
            return
        if self.table.identify_column(event.x) == '#1' and not self.busy:
            self.selected.symmetric_difference_update({key})
            self.table.set(key, 'selected', '☑' if key in self.selected else '☐')
        self.show_project(key)

    def toggle_all(self):
        if self.busy:
            return
        self.selected = set() if self.selected else {p.key for p in self.projects}
        for p in self.projects:
            self.table.set(p.key, 'selected', '☑' if p.key in self.selected else '☐')

    def launch(self):
        if self.busy:
            return
        try:
            if not self.projects or not self.selected:
                raise ValueError('请先扫描并勾选项目')
            self.runner = self.make_runner()
            if set(self.selected) - {p.key for p in self.runner.inspect()}:
                raise ValueError('项目目录已变化，请重新扫描')
            plan = self.runner.inspect()
            updates = ['%s: Step%d～Step%d 将重新执行' % (p.prefix, min(s.number for s in p.stages if s.plan_action=='RERUN'), max(s.number for s in p.stages if s.script)) for p in plan if any(s.plan_action=='RERUN' for s in p.stages)]
            self.log.insert('end', '\n'+'\n'.join(updates))
            mode, start, selected, continuing = self.mode.get(), self.start.get(), list(self.selected), self.continue_errors.get()
            self.busy = True
            self.run_button.state(['disabled'])
            self.scan_button.state(['disabled'])
            def work():
                try:
                    self.events.put(('done', self.runner.run(mode, start, selected, continuing)))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
            threading.Thread(target=work, daemon=False).start()
            self.status.set('；'.join(updates) if updates else '执行当前计划：未变化的有效阶段会显示 REUSED。')
        except Exception as exc:
            messagebox.showerror('无法启动', str(exc))

    def stop(self):
        if self.busy and self.runner:
            self.runner.stop.set()
            self.status.set('已请求安全停止，等待当前阶段完成；不会强制终止 CAE 保存。')

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'model_error':
                    messagebox.showerror('CAE GUI 启动失败', data)
                    continue
                if kind == 'update':
                    self.last_records[data['key']] = data
                    self.display_delivery(data)
                    self.refresh_delivery_row(data['key'])
                    states = [self.run_stage_label(s) for s in data['stages']]
                    for index, value in enumerate(states):
                        self.table.set(data['key'], ('part','assembly','analysis','hole','tie','step','bc','mesh','load')[index], value)
                    self.table.item(data['key'], tags=('failed',) if 'FAILED' in states else ('missing',) if 'MISSING' in states else ())
                    self.status.set(data['prefix'] + '  ' + ' / '.join(states))
                    self.log.delete('1.0', 'end')
                    self.log.insert('end', json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    self.busy = False
                    self.run_button.state(['!disabled'])
                    self.scan_button.state(['!disabled'])
                    if kind == 'migrated':
                        self.scan()
                        self.status.set('历史文件已内部归档，固定 CAE 已验证交付。')
                    elif kind == 'done':
                        self.report_dir = data[0]
                        self.projects = self.runner.inspect()
                        if any(any(s['status']=='SUCCESS' for s in p['stages']) for p in data[1]):
                            try:
                                save_successful_configuration(self.runner.executor.command, self.runner.executor.environment)
                            except OSError as exc:
                                self.log.insert('end', '\n无法保存启动器偏好：'+str(exc))
                        self.status.set('完成：' + str(self.report_dir) + '；' + ', '.join(p['prefix']+': '+p['result'] for p in data[1]))
                    else:
                        messagebox.showerror('批处理失败', data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def open_reports(self):
        path = self.report_dir or Path(self.output.get())
        if path and Path(path).is_dir():
            os.startfile(str(path))

    def toggle_advanced(self):
        if self.advanced.winfo_ismapped():
            self.advanced.grid_remove()
        else:
            self.advanced.grid(row=2,column=0,columnspan=7,sticky='ew',pady=5)

    @staticmethod
    def stage_label(stage):
        return stage.plan_action + (' / STALE' if stage.history_status == 'STALE' else '') if stage.status == 'READY' else stage.status

    @staticmethod
    def run_stage_label(row):
        if row.get('action') == 'REUSED' and row['status'] == 'SUCCESS':
            return 'REUSED'
        return ('RERUN / ' if row.get('action') == 'RERUN' else '')+row['status']

    def show_project(self, key):
        project=next(p for p in self.projects if p.key==key)
        self.display_delivery(dict(self.last_records.get(key, {}), key=key, prefix=project.prefix))
        self.details.delete(*self.details.get_children())
        for stage in project.stages:
            parent=self.details.insert('', 'end', text='Step%d — %s'%(stage.number,stage.status), values=('', '历史 '+str(stage.history_status or '无')))
            self.details.insert(parent,'end',text='PY',values=(stage.script or '暂缺','FOUND' if stage.script else 'MISSING'))
            self.details.insert(parent,'end',text='本阶段历史检查点',values=(stage.checkpoint.get('path') or '本轮生成',stage.checkpoint.get('state')))
            if stage.number > 1:
                upstream=project.stages[stage.number-2].checkpoint
                self.details.insert(parent,'end',text='上游 CAE',values=(upstream.get('path') or '等待上游生成',upstream.get('state')))
            for item in stage.inputs:
                label=('等待上游生成' if item.get('validation')=='WAITING_UPSTREAM' else '必需输入' if item['required'] else '可选生成来源')
                self.details.insert(parent,'end',text=label,values=(item['path']+' → '+item['relative'],item.get('validation', 'FOUND' if item['found'] else 'MISSING')))
                for candidate in item.get('expected',[]):
                    if not item['found']:
                        self.details.insert(parent,'end',text='预期位置',values=(candidate,''))
            for name in stage.embedded_inputs:
                self.details.insert(parent,'end',text='内嵌输入 '+name,values=(stage.script,'运行读取 PY 内嵌数据；同名外部计划不是必需文件'))
            for reason in stage.change_reasons:
                self.details.insert(parent,'end',text='重跑原因',values=(reason,stage.plan_action))
            for warning in stage.warnings:
                self.details.insert(parent,'end',text='兼容性提示',values=(warning,''))
            for name in stage.outputs:
                self.details.insert(parent,'end',text='本阶段输出',values=(name,'由本轮执行生成并校验'))
            for reason in stage.reasons:
                self.details.insert(parent,'end',text='预检查问题',values=(reason,stage.status))
        self.log.delete('1.0','end')
        errors=[s.history_error for s in project.stages if s.history_error]
        self.log.insert('end','\n'.join(errors) if errors else '预检查与历史结果分开展示。展开阶段可查看必需输入、可选来源及输出。')

    def show_errors(self):
        selection=self.table.selection()
        if not selection:
            return
        key=selection[0]
        record=self.last_records.get(key)
        self.log.delete('1.0','end')
        if record:
            self.log.insert('end','\n\n'.join('Step%d: %s'%(s['number'],s.get('error') or '; '.join(s['reasons'])) for s in record['stages'] if s.get('error') or s['reasons']))
            if record.get('delivery', {}).get('error'):
                self.log.insert('end', '\nCAE 交付：'+record['delivery']['error'])
        else:
            self.show_project(key)

    def available_models(self, key):
        from .publication import registry
        return registry(self.source.get(), key)

    def refresh_delivery_row(self, key):
        record = self.last_records.get(key, {})
        models = self.available_models(key)
        chosen = models.get('final') or models.get('partial') or {}
        self.table.set(key, 'completion', ('%d/9 ' % sum(s['status']=='SUCCESS' for s in record.get('stages', [])))+record.get('execution_result', '未运行')+' / '+record.get('result', '未交付'))
        self.table.set(key, 'model_path', chosen.get('path', '尚无固定交付；旧版本请迁移'))

    def display_delivery(self, record):
        delivery = record.get('delivery', {})
        count = sum(s['status']=='SUCCESS' for s in record.get('stages', []))
        models = self.available_models(record['key']) if record.get('key') else {}
        final, partial = models.get('final', {}), models.get('partial', {})
        self.delivery_text.set('最新运行：%s | PY %d/9 SUCCESS | 本次交付：%s\n此前/当前完整模型：%s\n当前阶段性模型（Step%s）：%s' % (
            record.get('execution_result', '未运行'), count, record.get('result', '未交付'),
            ((final.get('path') or '无') + ('（旧五阶段历史成果，不代表 V4 完成）' if final and final.get('stage',0)<9 else '')), partial.get('stage', '-'), partial.get('path') or '无'))

    def selected_delivery(self):
        selection = self.table.selection()
        if not selection:
            raise ValueError('请先选择项目')
        models = self.available_models(selection[0])
        return models.get('final') or models.get('partial') or {}

    def migrate_legacy(self):
        if self.busy:
            return
        try:
            from .migration import plan_migration, apply_migration
            path, plan = plan_migration(self.source.get())
            self.log.delete('1.0', 'end')
            self.log.insert('end', json.dumps(plan, ensure_ascii=False, indent=2))
            lines = [Path(f['path']).name+' | '+f['validation']+' | '+f['action'] for f in plan['files']]
            if not plan['selected']:
                raise ValueError('没有可确认的完整成功模型，请检查运行记录。')
            prompt = '\n'.join(lines)+'\n\n将最新完整成功模型重新验证后发布为固定 final.cae，其余列出的历史文件内部归档，不删除。\n清单：'+str(path)+'\n确认迁移？'
            if not messagebox.askyesno('确认历史文件迁移清单', prompt):
                return
            executor = self.make_runner().executor
            self.busy = True
            self.run_button.state(['disabled']); self.scan_button.state(['disabled'])
            def work():
                try:
                    result = apply_migration(path, executor, confirmed=True)
                    self.events.put(('migrated', result))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
            threading.Thread(target=work, daemon=False).start()
        except Exception as exc:
            messagebox.showerror('迁移未执行', str(exc))

    def open_results(self):
        path = Path(self.source.get())/'CAE_Results'
        if path.is_dir():
            os.startfile(str(path))
        else:
            messagebox.showerror('尚无交付文件', 'CAE_Results 尚未生成，请先运行。')

    def show_delivery(self):
        try:
            selection = self.table.selection()
            delivery = dict(latest_run=self.last_records.get(selection[0], {}) if selection else {}, available=self.available_models(selection[0]) if selection else {})
            self.log.delete('1.0', 'end')
            self.log.insert('end', json.dumps(delivery, ensure_ascii=False, indent=2))
        except ValueError as exc:
            messagebox.showerror('模型交付', str(exc))

    def open_final(self):
        if self.busy:
            messagebox.showinfo('正在运行', '请等待模型交付验证完成。')
            return
        try:
            from .delivery import open_model
            selected = self.selected_delivery()
            if selected.get('stage', 0) < 9:
                messagebox.showinfo('阶段性模型', '该项目当前仅完成 Step%d，将打开阶段性 CAE。' % selected['stage'])
            process = open_model(self.make_runner().executor, selected)
            def monitor():
                code = process.wait()
                if code:
                    self.events.put(('model_error', 'Abaqus GUI 启动器退出码 %s。请检查版本、许可和启动器配置；模型交付详情保存了验证日志。' % code))
            threading.Thread(target=monitor, daemon=True).start()
        except (OSError, ValueError) as exc:
            messagebox.showerror('无法打开 CAE 模型', str(exc))

    def close(self):
        if self.busy:
            self.stop()
            messagebox.showinfo('等待安全停止', '已请求停止。当前阶段结束后再关闭窗口，避免损坏正在保存的模型。')
        else:
            self.root.destroy()

def main():
    root = tk.Tk()
    BatchRunnerGUI(root)
    root.mainloop()
