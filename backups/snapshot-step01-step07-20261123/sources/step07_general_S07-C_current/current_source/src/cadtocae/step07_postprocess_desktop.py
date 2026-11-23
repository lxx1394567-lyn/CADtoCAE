"""Stage07 UI. Automatic work runs in a separate CAE process, never the user's MDB."""
import json, os, queue, subprocess, threading, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .step07_postprocess import generate_postprocess

class PostprocessWindow(tk.Toplevel):
    def __init__(self,parent,folder='',summary=''):
        super().__init__(parent);self.title('07 ODB结果提取 — 只读后处理');self.geometry('1000x700')
        self.events=queue.Queue();self.running=False;self.result=None
        self.values={};self.widgets={};self.catalog={}
        form=ttk.Frame(self,padding=12);form.pack(fill='x');form.columnconfigure(1,weight=1)
        fields=[('odb','ODB 文件',''),('summary','Assembly Summary',summary),('output','项目输出文件夹',folder),('job_id','结果 Job ID（区分折减/厚度方案）',''),('case_label','工况说明（人工核对）',''),('step','分析步（留空=最终步）',''),('frame','帧编号（从0开始；-1=最后有效帧）','-1'),('stress_max','统一应力色阶上限 MPa（留空=自动）',''),('abaqus','Abaqus 命令',r'D:\Software\SIMULIA\Commands\abaqus.bat')]
        for i,(key,title,value) in enumerate(fields):
            v=tk.StringVar(value=value);self.values[key]=v
            ttk.Label(form,text=title).grid(row=i,column=0,sticky='w',pady=4)
            w=ttk.Combobox(form,textvariable=v) if key in ('step','frame') else ttk.Entry(form,textvariable=v)
            w.grid(row=i,column=1,sticky='ew',padx=8);self.widgets[key]=w
            if key in ('odb','summary','output','abaqus'):ttk.Button(form,text='选择',command=lambda k=key:self.choose(k)).grid(row=i,column=2)
        ttk.Label(self,text='只读 ODB；不打开/保存 CAE，不提交计算。计算必须完成。峰值取原始积分点；安全系数等待材料强度确认。',wraplength=950).pack(fill='x',padx=12)
        bar=ttk.Frame(self,padding=12);bar.pack(fill='x');self.buttons=[]
        for label,command in [('读取分析步/帧',self.inspect),('生成后处理 PY',self.generate),('执行后处理（独立进程）',self.run),('打开结果文件夹',self.open_results)]:
            b=ttk.Button(bar,text=label,command=command);b.pack(side='left',padx=4);self.buttons.append(b)
        self.progress=ttk.Progressbar(self,mode='indeterminate');self.progress.pack(fill='x',padx=12)
        self.log=tk.Text(self,wrap='word',height=18);self.log.pack(fill='both',expand=True,padx=12,pady=12)
        self.protocol('WM_DELETE_WINDOW',self.close);self.after(150,self.poll)
        self.widgets['step'].bind('<<ComboboxSelected>>',self.step_changed)
    def step_changed(self,*_):
        name=self.values['step'].get();frames=self.catalog.get(name,[])
        self.widgets['frame']['values']=[str(x['index']) for x in frames]
        self.values['frame'].set('-1')
        self.note(name+': '+str(frames))
    def inspect(self):
        if self.running:return
        odb=self.values['odb'].get();command=self.values['abaqus'].get()
        if not Path(odb).is_file() or not Path(command).is_file():messagebox.showerror('路径无效','请选择有效 ODB 和 Abaqus 命令',parent=self);return
        root=Path(self.values['output'].get())/'Step07_ODB_Results'/'Runtime_Logs';root.mkdir(parents=True,exist_ok=True)
        base=root/('metadata_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));script=base.with_suffix('.py');report=base.with_suffix('.json')
        code="import json,traceback\nfrom odbAccess import openOdb\nc=json.loads(%r)\nr={}\no=None\ntry:\n o=openOdb(path=c['odb'].encode('mbcs'),readOnly=True)\n r['steps']={k:[dict(index=i,time=f.frameValue,fields=list(f.fieldOutputs.keys())) for i,f in enumerate(s.frames)] for k,s in o.steps.items()}\n r['status']=str(o.diagnosticData.jobStatus)\nexcept:\n r['error']=traceback.format_exc()\nfinally:\n if o is not None:o.close()\n json.dump(r,open(c['report'],'w'),indent=2)\n"%json.dumps({'odb':odb,'report':str(report)},ensure_ascii=True)
        script.write_text(code,encoding='utf-8');self.running=True;self.progress.start(15)
        def work():
            try:
                p=subprocess.run([command,'python',str(script)],cwd=str(root),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if not report.is_file():raise RuntimeError(p.stdout)
                self.events.put(('catalog',json.loads(report.read_text())))
            except Exception as e:self.events.put(('log','读取失败：'+str(e)))
            self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def choose(self,key):
        if self.running:return
        if key=='output':p=filedialog.askdirectory(parent=self,initialdir=self.values['output'].get())
        else:p=filedialog.askopenfilename(parent=self,initialdir=self.values['output'].get(),filetypes=[('ODB','*.odb')] if key=='odb' else [('JSON','*.json')] if key=='summary' else [('Command','*.bat *.exe')])
        if p:
            self.values[key].set(p)
            if key=='odb':self.values['job_id'].set(Path(p).stem)
    def note(self,s):self.log.insert('end',s+'\n');self.log.see('end')
    def generate(self):
        if self.running:return None
        try:
            v={k:x.get().strip() for k,x in self.values.items()}
            self.result=generate_postprocess(v['summary'],v['odb'],v['output'],v['step'],int(v['frame']),v['job_id'],v['case_label'],float(v['stress_max']) if v['stress_max'] else None)
            self.note('已生成：'+self.result['script']+'\n结果目录：'+self.result['plan']['output_root']+'\\'+self.result['plan']['job_id']+'（重跑保留旧结果并使用版本后缀）')
            return self.result
        except Exception as e:messagebox.showerror('生成失败',str(e),parent=self);return None
    def run(self):
        r=self.generate()
        if not r:return
        command=self.values['abaqus'].get()
        if not Path(command).is_file():messagebox.showerror('未找到 Abaqus',command,parent=self);return
        self.running=True;self.progress.start(15)
        for b in self.buttons:b.configure(state='disabled')
        # Keep Abaqus journal/replay files out of the user's project root.
        logs=Path(r['plan']['output_root'])/'Runtime_Logs';logs.mkdir(parents=True,exist_ok=True)
        prior=set(logs.parent.glob('*/results.json'))
        def work():
            try:
                p=subprocess.Popen([command,'cae','noGUI='+r['script']],cwd=str(logs),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in p.stdout:self.events.put(('log',line.rstrip()))
                code=p.wait()
                new=set(logs.parent.glob('*/results.json'))-prior
                matching=[]
                for path in new:
                    result=json.loads(path.read_text(encoding='utf-8'))
                    if result.get('plan',{}).get('job_id')==r['plan']['job_id']:
                        matching.append(result);self.events.put(('log',result['status']+'：'+str(path.parent)))
                if not matching:self.events.put(('log','FAILED: 未发现本次结果报告；返回码 %d。'%code))
            except Exception as e:self.events.put(('log','FAILED: '+str(e)))
            self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:
            while True:
                k,v=self.events.get_nowait()
                if k=='done':
                    self.running=False;self.progress.stop()
                    for b in self.buttons:b.configure(state='normal')
                elif k=='catalog':
                    if 'error' in v:self.note(v['error'])
                    else:
                        self.catalog=v['steps'];self.widgets['step']['values']=list(self.catalog)
                        self.note('计算状态：'+v['status']+'；可选择分析步和帧。默认留空分析步/-1帧读取最终有效结果。')
                else:self.note(v)
        except queue.Empty:pass
        self.after(150,self.poll)
    def open_results(self):
        p=Path(self.values['output'].get())/'Step07_ODB_Results'
        if p.is_dir():os.startfile(str(p))
    def close(self):
        if self.running:messagebox.showinfo('正在后处理','请等待独立后处理结束；用户 Abaqus 会话不受影响。',parent=self)
        else:self.destroy()
