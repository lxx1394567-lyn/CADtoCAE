# -*- coding: utf-8 -*-
"""Step07 folder scanner and sequential setup GUI; no analysis parameter editors."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.step07_batch import scan_projects,run_batch
from cadtocae.step07_desktop import abaqus_command
from cadtocae.step07_mesh_desktop import scan_mesh_projects,generate_mesh_projects,validate_accepted
from cadtocae.step07_mesh_setup import generate_stage3
VERSION='0.5.2'

class Step07App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('CADtoCAE Step07 '+VERSION+' — 分阶段 PY 生成')
        self.geometry('1150x760');self.minsize(900,600)
        self.folder=tk.StringVar();self.status=tk.StringVar(value='选择工作文件夹，扫描后勾选项目，默认只生成 PY；自动运行是可选操作。')
        self.events=queue.Queue();self.busy=False;self.scan=None;self.output=None;self.poll_count=0;self.completed_batch=False
        bar=ttk.Frame(self,padding=12);bar.pack(fill='x');bar.columnconfigure(1,weight=1)
        ttk.Label(bar,text='工作文件夹').grid(row=0,column=0)
        self.entry=ttk.Entry(bar,textvariable=self.folder);self.entry.grid(row=0,column=1,sticky='ew',padx=8)
        self.choose_button=ttk.Button(bar,text='选择文件夹',command=self.choose);self.choose_button.grid(row=0,column=2,padx=4)
        self.scan_button=ttk.Button(bar,text='扫描项目',command=self.start_scan);self.scan_button.grid(row=0,column=3)
        ttk.Label(self,text='完整项目编号匹配 · 自动识别文件 · 当前阶段只需 CAE 与项目摘要，不要求荷载').pack(anchor='w',padx=12)
        phases=ttk.Frame(self,padding=(12,4));phases.pack(fill='x')
        self.stage=tk.IntVar(value=1)
        self.phase_buttons=[];self.preselected_mesh_input=None
        for n,label in enumerate(('① 计算步','② 边界条件（独立PY）','③ 网格划分','④ 荷载施加','⑤ 生成 INP'),1):
            button=ttk.Radiobutton(phases,text=label,variable=self.stage,value=n,command=self.stage_changed,state='normal' if n in (1,3) else 'disabled')
            button.pack(side='left',padx=6);self.phase_buttons.append(button)
        frame=ttk.Frame(self,padding=12);frame.pack(fill='both',expand=True)
        self.table=ttk.Treeview(frame,columns=('selected','project','check','state'),show='headings',selectmode='extended')
        for k,label,w in [('selected','执行',65),('project','完整项目编号',450),('check','文件检查',320),('state','执行状态',100)]:
            self.table.heading(k,text=label);self.table.column(k,width=w)
        self.table.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',self.details);self.table.bind('<Double-1>',self.toggle)
        bar=ttk.Frame(self,padding=(12,0));bar.pack(fill='x')
        self.toggle_button=ttk.Button(bar,text='勾选 / 取消所选',command=self.toggle);self.toggle_button.pack(side='left')
        self.run_button=ttk.Button(bar,text='生成当前会话 PY（默认）',command=self.start_batch);self.run_button.pack(side='left',padx=10)
        self.auto_button=ttk.Button(bar,text='独立 CAE 自动运行',command=lambda:self.start_batch('automatic'));self.auto_button.pack(side='left',padx=(0,10))
        self.open_button=ttk.Button(bar,text='打开输出文件夹',command=self.open_output);self.open_button.pack(side='left')
        ttk.Label(self,textvariable=self.status,wraplength=1100).pack(fill='x',padx=12,pady=8)
        self.log=tk.Text(self,height=13,wrap='word',state='disabled');self.log.pack(fill='both',expand=True,padx=12,pady=(0,12))
        self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll);self.controls()
        self.append('默认生成 CURRENT_SESSION_DEBUG PY，使用 ABAQUS 当前已加载的目标 Model；不启动 ABAQUS。GENERATED 表示尚未执行；SUCCESS 表示自动执行及重开通过。')
    def append(self,text):
        self.log.configure(state='normal');self.log.insert('end',str(text)+'\n');self.log.see('end');self.log.configure(state='disabled')
    def controls(self):
        state='disabled' if self.busy else 'normal'
        for w in (self.entry,self.choose_button,self.scan_button,self.toggle_button):w.configure(state=state)
        self.run_button.configure(state='normal' if not self.busy and self.scan and any(r['ready'] and r['selected'] for r in self.scan['projects']) else 'disabled')
        self.auto_button.configure(state=self.run_button['state'])
        if self.stage.get()==3:self.auto_button.configure(state='disabled')
        for n,button in enumerate(self.phase_buttons,1):button.configure(state='normal' if not self.busy and n in (1,3) else 'disabled')
        self.open_button.configure(state='normal' if self.output else 'disabled')
    def choose(self):
        path=filedialog.askdirectory(parent=self,title='选择 Step07 工作文件夹')
        if path:self.folder.set(path);self.start_scan()
    def background(self,fn,kind):
        self.busy=True;self.controls()
        def work():
            try:self.events.put((kind,fn()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()
    def start_scan(self):
        if self.busy:return
        folder=self.folder.get();self.status.set('正在递归扫描完整项目编号…');self.completed_batch=False
        stage=self.stage.get()
        self.background(lambda:scan_mesh_projects(folder) if stage==3 else scan_projects(folder),'scan')
    def stage_changed(self):
        self.scan=None;self.table.delete(*self.table.get_children());self.controls()
        if self.folder.get():self.start_scan()
    def render(self):
        self.table.delete(*self.table.get_children())
        for i,r in enumerate(self.scan['projects']):self.row(i,r)
    def row(self,i,r):
        values=('☑' if r['selected'] and r['ready'] else '☐',r['project_id'],r['reason'],r['status'])
        if self.table.exists(str(i)):self.table.item(str(i),values=values)
        else:self.table.insert('','end',iid=str(i),values=values)
    def details(self,*_):
        if not self.scan:return
        for iid in self.table.selection():
            r=self.scan['projects'][int(iid)];self.append(r['project_id']+' | '+r['reason']+'\n来源：'+r['source_folder'])
            for k,v in r['files'].items():self.append(k+'：'+v)
            for warning in r['warnings']:self.append('提示：'+warning)
    def toggle(self,*_):
        if self.busy or not self.scan:return
        for iid in self.table.selection():
            r=self.scan['projects'][int(iid)]
            if r['ready']:r['selected']=not r['selected'];self.row(int(iid),r)
        self.controls()
    def start_batch(self,mode='generate'):
        if self.busy or not self.scan:return
        if str(Path(self.folder.get()).resolve())!=self.scan['root']:
            self.append('工作文件夹已改变，请重新扫描');return
        if self.stage.get()==3:
            accepted={}
            for row in self.scan['projects']:
                if not row['ready'] or not row['selected']:continue
                path=self.preselected_mesh_input or filedialog.askopenfilename(parent=self,title=row['project_id']+'：选择已人工验收的 Step07-02 CAE',initialdir=str(Path(row['source_folder'])/'CAE_Results'),filetypes=[('CAE','*.cae')])
                if not path:continue
                try:accepted[row['key']]=validate_accepted(row,path)
                except Exception as exc:self.append(str(exc));return
            if not accepted:return
            self.completed_batch=False;self.status.set('正在生成 Step07-03 PY；不启动 ABAQUS。')
            self.background(lambda:generate_mesh_projects(self.scan,accepted,lambda e:self.events.put(('progress',e))),'batch');return
        command=''
        if mode=='automatic':
            try:command=abaqus_command(os.environ.get('CADTOCAE_ABAQUS_COMMAND','') or shutil.which('abaqus') or '')
            except Exception as exc:self.append(str(exc)+'；可由维护人员设置 CADTOCAE_ABAQUS_COMMAND。');return
        selected={r['key'] for r in self.scan['projects'] if r['ready'] and r['selected']}
        if not selected:return
        self.completed_batch=False;self.status.set('正在生成独立 PY…' if mode=='generate' else '自动运行 Step07-1，完成后停止。')
        self.background(lambda:run_batch(self.scan,selected,command,lambda e:self.events.put(('progress',e)),mode=mode),'batch')
    def poll(self):
        self.poll_count+=1
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    if 'log' in value:self.append(value['log'])
                    if 'row' in value:
                        r=value['row']
                        for i,old in enumerate(self.scan['projects']):
                            if old['key']==r['key']:self.row(i,r);break
                        self.append(r['project_id']+' '+r['status']+' '+r['reason'])
                elif kind=='error':self.busy=False;self.status.set('失败：'+value);self.append(value);self.controls()
                else:
                    self.busy=False;self.scan=value;self.render()
                    if kind=='batch':
                        self.output=value['output_folder'];self.completed_batch=True
                        self.status.set('批次完成：'+json.dumps(value['counts'],ensure_ascii=False))
                        session=dict(frozen=bool(getattr(sys,'frozen',False)),executable=sys.executable,ui_poll_count=self.poll_count,version=VERSION,result=value)
                        for row in value['projects']:
                            if row.get('generation_report'):
                                path=Path(row['generation_report']).with_suffix('.desktop.json')
                                with path.open('x',encoding='utf-8') as handle:json.dump(dict(frozen=session['frozen'],version=VERSION,executable=sys.executable,ui_poll_count=self.poll_count,result=row),handle,ensure_ascii=False,indent=2)
                    else:self.status.set('扫描完成：%d 个项目，%d 个可执行。选择行查看文件和原因。'%(len(value['projects']),sum(r['ready'] for r in value['projects'])))
                    self.controls()
        except queue.Empty:pass
        self.after(100,self.poll)
    def open_output(self):
        if self.output:os.startfile(self.output)
    def close(self):
        if self.busy:messagebox.showinfo('Step07','请等待当前批次完成。',parent=self);return
        self.destroy()

def main():
    if '--odb-postprocess-summary' in sys.argv:
        from cadtocae.step07_postprocess import generate_postprocess
        q=argparse.ArgumentParser();q.add_argument('--odb-postprocess-summary',required=True);q.add_argument('--odb',required=True);q.add_argument('--output',required=True);q.add_argument('--step',default='');q.add_argument('--frame',type=int,default=-1);q.add_argument('--job-id',default='');q.add_argument('--case-label',default='');q.add_argument('--report',required=True)
        a=q.parse_args();r=generate_postprocess(a.odb_postprocess_summary,a.odb,a.output,a.step,a.frame,a.job_id,a.case_label)
        with open(a.report,'x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
        return 0
    if '--inplace-summary' in sys.argv:
        from cadtocae.step07_inplace import generate_inplace
        q=argparse.ArgumentParser();q.add_argument('--inplace-summary',required=True);q.add_argument('--load-workbook');q.add_argument('--selected-cae');q.add_argument('--job-id',default='J13');q.add_argument('--hole-report',required=True);q.add_argument('--output',required=True);q.add_argument('--stage',type=int,default=0);q.add_argument('--overwrite',action='store_true');q.add_argument('--report',required=True)
        args=q.parse_args();result=generate_inplace(args.inplace_summary,args.output,args.hole_report,args.stage,args.overwrite,args.load_workbook,args.job_id,args.selected_cae)
        with Path(args.report).open('x',encoding='utf-8') as f:json.dump(dict(frozen=bool(getattr(sys,'frozen',False)),result=result),f,indent=2)
        return 0
    if getattr(sys,'frozen',False) and len(sys.argv)>1 and '--pipeline-ui-smoke' not in sys.argv:
        raise ValueError('USER_EXE_GENERATION_ONLY: legacy automation is available only through development source tools')
    if '--pipeline-ui-smoke' in sys.argv:
        from cadtocae.step07_pipeline_desktop import PipelineApp
        q=argparse.ArgumentParser();q.add_argument('--pipeline-ui-smoke',action='store_true');q.add_argument('--report',required=True)
        args=q.parse_args();app=PipelineApp()
        def complete():
            app.update_idletasks()
            with Path(args.report).open('x',encoding='utf-8') as f:json.dump(dict(frozen=bool(getattr(sys,'frozen',False)),title=app.title(),mapped=bool(app.winfo_ismapped()),stage_choices=list(app.combo['values']),status='GUI_STARTED'),f,ensure_ascii=False,indent=2)
            app.destroy()
        app.after(1500,complete);app.mainloop();return 0
    if len(sys.argv)==1:
        from cadtocae.step07_pipeline_desktop import PipelineApp
        PipelineApp().mainloop();return 0
    if '--pipeline-summary' in sys.argv:
        from cadtocae.step07_pipeline import generate_pipeline
        q=argparse.ArgumentParser();q.add_argument('--pipeline-summary',required=True);q.add_argument('--input-cae',required=True);q.add_argument('--hole-report',required=True);q.add_argument('--output',required=True);q.add_argument('--stage',type=int,default=0);q.add_argument('--predecessor-report');q.add_argument('--report',required=True)
        args=q.parse_args();result=generate_pipeline(args.pipeline_summary,args.input_cae,args.output,args.hole_report,args.stage,args.predecessor_report)
        with Path(args.report).open('x',encoding='utf-8') as f:json.dump(dict(frozen=bool(getattr(sys,'frozen',False)),result=result),f,indent=2)
        return 0
    p=argparse.ArgumentParser();p.add_argument('--folder');p.add_argument('--scan');p.add_argument('--run',action='store_true',help='Generate scripts; add --automatic to execute');p.add_argument('--automatic',action='store_true');p.add_argument('--report');p.add_argument('--ui-smoke',action='store_true')
    p.add_argument('--stage',type=int,choices=(1,3),default=1);p.add_argument('--accepted-cae');p.add_argument('--mesh-summary');p.add_argument('--output')
    a=p.parse_args()
    if a.mesh_summary:
        if not a.accepted_cae or not a.output:raise ValueError('mesh generation requires --accepted-cae and --output')
        result=generate_stage3(a.mesh_summary,a.accepted_cae,a.output)
        if a.report:
            with Path(a.report).open('x',encoding='utf-8') as f:json.dump(dict(frozen=bool(getattr(sys,'frozen',False)),result=result),f,indent=2)
        return 0
    if a.scan:
        result=scan_mesh_projects(a.scan) if a.stage==3 else scan_projects(a.scan)
        if a.stage==3 and a.run:raise ValueError('Use --mesh-summary with explicitly accepted CAE for mesh generation')
        if a.run:result=run_batch(result,{r['key'] for r in result['projects'] if r['ready']},abaqus_command(os.environ.get('CADTOCAE_ABAQUS_COMMAND','') or shutil.which('abaqus') or '') if a.automatic else '',mode='automatic' if a.automatic else 'generate')
        if a.report:Path(a.report).write_text(json.dumps(dict(frozen=bool(getattr(sys,'frozen',False)),executable=sys.executable,result=result),ensure_ascii=False,indent=2),encoding='utf-8')
        return 1 if result.get('counts',{}).get('FAILED') else 0
    app=Step07App()
    app.stage.set(a.stage);app.preselected_mesh_input=a.accepted_cae if a.ui_smoke else None;app.controls()
    if a.folder:app.folder.set(a.folder);app.after(150,app.start_scan)
    # Explicit packaged GUI callback regression, following Step06 smoke-test convention.
    # Normal launch and --folder NEVER execute automatically.
    if a.ui_smoke:
        if not a.folder or not a.report:raise ValueError('--ui-smoke requires --folder and --report')
        stage=[0]
        def smoke():
            if not app.busy and app.scan:
                if stage[0]==0:
                    stage[0]=1;(app.auto_button if a.automatic else app.run_button).invoke()
                elif app.completed_batch:
                    Path(a.report).write_text(json.dumps(dict(frozen=bool(getattr(sys,'frozen',False)),executable=sys.executable,ui_poll_count=app.poll_count,result=app.scan),ensure_ascii=False,indent=2),encoding='utf-8');return
            app.after(200,smoke)
        app.after(400,smoke)
    app.mainloop();return 0
if __name__=='__main__':sys.exit(main())
