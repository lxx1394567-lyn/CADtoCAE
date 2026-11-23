"""Six-stage current-MDB script generation UI. Does not open CAE or run Abaqus."""
import json,os,threading,queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .step07_inplace import generate_inplace
from .step07_projects import scan_inplace
class PipelineApp(tk.Tk):
    def __init__(self):
        super().__init__();self.title('CADtoCAE Step07 0.9.3 — Tie / 分析步 / BC / Mesh / POS-NEG / INP / ODB');self.geometry('1250x720')
        self.folder=tk.StringVar();self.stage=tk.StringVar(value='全部：01 → 06');self.events=queue.Queue();self.rows={};self.busy=False
        bar=ttk.Frame(self,padding=10);bar.pack(fill='x')
        ttk.Entry(bar,textvariable=self.folder).pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='选择工作文件夹',command=self.choose).pack(side='left');ttk.Button(bar,text='扫描项目',command=self.scan).pack(side='left')
        ttk.Label(self,text='默认输出目录 = 当前工作文件夹；CAE只关联，不由EXE打开。实际Model、装配、开孔在运行PY前核验。').pack(anchor='w',padx=10)
        cols=('project','cae','state');self.table=ttk.Treeview(self,columns=cols,show='headings',selectmode='extended')
        for key,title,width in [('project','完整项目编号 / 目标 Model',330),('cae','已关联 CAE（可选择非标准文件名）',600),('state','六阶段生成状态',240)]:self.table.heading(key,text=title);self.table.column(key,width=width)
        self.table.pack(fill='both',expand=True,padx=10)
        bar=ttk.Frame(self,padding=10);bar.pack(fill='x')
        ttk.Button(bar,text='选择当前项目 CAE',command=self.select_cae).pack(side='left',padx=5)
        self.combo=ttk.Combobox(bar,textvariable=self.stage,state='readonly',values=['全部：01 → 06','01 Tie','02 分析步','03 边界条件','04 网格','05 POS/NEG 双工况','06 当前工况 INP','07 ODB结果提取'],width=22);self.combo.pack(side='left')
        self.button=ttk.Button(bar,text='生成 PY',command=self.generate);self.button.pack(side='left',padx=10)
        ttk.Button(bar,text='打开输出文件夹',command=lambda:os.startfile(self.folder.get())).pack(side='left')
        self.log=tk.Text(self,height=16,wrap='word');self.log.pack(fill='both',expand=True,padx=10,pady=10)
        self.note('01 Tie → 02 分析步 → 03 BC → 04 Mesh → 05 POS/NEG → 06 INP。只生成PY/配置，不启动Abaqus、不保存CAE、不提交。每步人工检查并保存。已有文件内容不变时不重写；更新前备份至Step07_Archive。')
        self.after(100,self.poll)
    def note(self,t):self.log.insert('end',str(t)+'\n');self.log.see('end')
    def choose(self):
        p=filedialog.askdirectory(parent=self)
        if p:self.folder.set(p);self.scan()
    def scan(self):
        if self.busy:return
        try:
            rows=scan_inplace(self.folder.get());self.table.delete(*self.table.get_children());self.rows={}
            for r in rows:
                key=self.table.insert('','end',values=(r['project'],r['cae'] or '请明确选择（%d个候选）'%len(r['candidates']),'待生成' if r['ready'] else '缺少/不匹配开孔报告'));self.rows[key]=r
            self.note('扫描完成：%d 个项目。目标Model取自Assembly Summary；不能仅凭CAE文件名认定已开孔。'%len(rows))
        except Exception as e:self.note('FAILED: '+str(e))
    def select_cae(self):
        if self.busy:return
        for key in self.table.selection():
            r=self.rows[key];p=filedialog.askopenfilename(parent=self,title=r['project']+'：明确选择已完成开孔并人工保存的CAE',initialdir=self.folder.get(),filetypes=[('CAE','*.cae')])
            if p:r['cae']=str(Path(p).resolve());self.table.set(key,'cae',r['cae']);self.note('已关联 '+r['cae']+'；内部Model/开孔待当前MDB运行核验，不重命名文件。')
    def generate(self):
        if self.busy:return
        if self.stage.get().startswith('07'):
            from .step07_postprocess_desktop import PostprocessWindow
            selected=self.table.selection()
            summary=self.rows[selected[0]]['summary'] if selected else ''
            PostprocessWindow(self,self.folder.get(),summary);return
        n=0 if self.stage.get().startswith('全部') else int(self.stage.get()[:2]);tasks=[]
        for key in self.table.selection():
            r=self.rows[key]
            if not r['ready']:self.note(r['project']+'：缺少有效开孔报告');continue
            if not r['cae']:
                self.select_cae()
                if not r['cae']:continue
            workbook=None
            if n in (0,5,6):
                workbook=filedialog.askopenfilename(parent=self,title=r['project']+'：荷载Excel（取消使用已配置来源，无来源则等待输入）',initialdir=self.folder.get(),filetypes=[('Excel','*.xlsx')]) or None
            tasks.append((key,r,workbook))
        if not tasks:return
        self.busy=True;self.button.configure(state='disabled');output_folder=self.folder.get()
        def worker():
            for key,r,workbook in tasks:
                args=(r['summary'],output_folder,r['holes'],n)
                try:
                    try:result=generate_inplace(*args,load_workbook=workbook,selected_cae=r['cae'])
                    except ValueError as e:
                        if 'OVERWRITE_CONFIRMATION_REQUIRED' not in str(e):raise
                        answer=threading.Event();box={};self.events.put(('approval',r['project'],answer,box));answer.wait()
                        if not box.get('yes'):self.events.put(('log','取消更新：'+r['project']));continue
                        result=generate_inplace(*args,overwrite=True,load_workbook=workbook,selected_cae=r['cae'])
                    self.events.put(('done',key,result))
                except Exception as e:self.events.put(('log','FAILED: '+str(e)))
            self.events.put(('idle',))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            while True:
                item=self.events.get_nowait();kind=item[0]
                if kind=='approval':
                    _,p,event,box=item;box['yes']=messagebox.askyesno('受控更新',p+'：文件内容已变化。是否先备份旧PY/配置到Step07_Archive，再更新？不修改CAE。',parent=self);event.set()
                elif kind=='done':
                    _,key,r=item;self.table.set(key,'state',r['file_update']['status']);self.note(r['file_update']['status']+'\n'+'\n'.join(x['script'] for x in r['stages'])+'\n荷载状态：'+r['load_status'])
                elif kind=='idle':self.busy=False;self.button.configure(state='normal')
                else:self.note(item[1])
        except queue.Empty:pass
        self.after(100,self.poll)
