"""Step04 folder GUI; no placement logic."""
from __future__ import annotations
import argparse
import json
import queue
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, ttk
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cadtocae.assembly_projects import can_generate, generate_batch, project_details, scan_projects

class Step04AssemblyScriptApp(Tk):
    def __init__(self):
        super().__init__()
        self.title('CADtoCAE Step04 vNext — Assembly Script Generator')
        self.geometry('1280x780'); self.minsize(1000,640)
        self.folder=StringVar(); self.recursive=BooleanVar(value=False)
        self.status=StringVar(value='Select a Project Folder, then Scan Projects.')
        self.scan=None; self.busy=False; self.events=queue.Queue()
        top=ttk.Frame(self,padding=12); top.pack(fill='x'); top.columnconfigure(1,weight=1)
        ttk.Label(top,text='Project Folder:').grid(row=0,column=0)
        entry=ttk.Entry(top,textvariable=self.folder); entry.grid(row=0,column=1,sticky='ew',padx=10)
        select=ttk.Button(top,text='Select Folder',command=self.choose_folder); select.grid(row=0,column=2)
        recursive=ttk.Checkbutton(top,text='Include Subfolders (default OFF)',variable=self.recursive)
        recursive.grid(row=1,column=1,sticky='w',pady=8)
        self.inputs=[entry,select,recursive]
        self.scan_button=ttk.Button(top,text='Scan Projects',command=self.start_scan); self.scan_button.grid(row=1,column=2)
        frame=ttk.Frame(self); frame.pack(fill='both',expand=True,padx=12)
        frame.columnconfigure(0,weight=1); frame.rowconfigure(0,weight=1)
        columns=('project','structure','input','capability','generation','result')
        self.table=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse',height=12)
        for key,label,width in zip(columns,('Project ID','Structure','Input','Capability','Generation','Result'),(360,85,160,110,110,340)):
            self.table.heading(key,text=label); self.table.column(key,width=width,minwidth=70,stretch=False)
        self.table.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(frame,orient='vertical',command=self.table.yview); vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=self.table.xview); horizontal.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.table.bind('<<TreeviewSelect>>',self.details)
        actions=ttk.Frame(self,padding=12); actions.pack(fill='x')
        self.selected_button=ttk.Button(actions,text='Generate Selected',command=lambda:self.start_generate(True)); self.selected_button.pack(side='left')
        self.all_button=ttk.Button(actions,text='Generate All Ready',command=lambda:self.start_generate(False)); self.all_button.pack(side='left',padx=10)
        self.progress=ttk.Progressbar(actions,mode='indeterminate',length=100); self.progress.pack(side='left',padx=10)
        ttk.Label(actions,textvariable=self.status).pack(side='left')
        logs=ttk.LabelFrame(self,text='Process Log',padding=5); logs.pack(fill='both',expand=True,padx=12,pady=(0,12))
        self.log=Text(logs,height=12,wrap='word',state='disabled'); self.log.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(logs,command=self.log.yview); scroll.pack(side='right',fill='y'); self.log.configure(yscrollcommand=scroll.set)
        self.folder.trace_add('write',self.invalidate); self.recursive.trace_add('write',self.invalidate)
        self.protocol('WM_DELETE_WINDOW',self.close); self.buttons(); self.after(100,self.poll)

    def choose_folder(self):
        value=filedialog.askdirectory(parent=self,title='Select Project Folder')
        if value:self.folder.set(value)

    def invalidate(self,*_):
        self.scan=None; self.table.delete(*self.table.get_children())
        self.status.set('Folder settings changed. Scan Projects to refresh.'); self.buttons()

    def buttons(self):
        self.scan_button.configure(state='disabled' if self.busy else 'normal')
        for widget in self.inputs:widget.configure(state='disabled' if self.busy else 'normal')
        available=self.scan is not None and not self.busy
        self.selected_button.configure(state='normal' if available and self.table.selection() else 'disabled')
        self.all_button.configure(state='normal' if available and any(can_generate(r) for r in self.scan['projects']) else 'disabled')

    def append_log(self,text):
        self.log.configure(state='normal'); self.log.insert('end',text.rstrip()+'\n'); self.log.see('end'); self.log.configure(state='disabled')

    @staticmethod
    def row_values(row):
        return tuple(row[k] for k in ('project_id','structure_type','input_status','capability','generation_status','result'))

    def run(self,operation,action):
        if self.busy:return
        self.busy=True; self.buttons(); self.progress.start(12)
        def work():
            try:self.events.put((operation,action()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def start_scan(self):
        if self.busy:return
        folder,recursive=self.folder.get().strip(),self.recursive.get()
        if not folder:self.append_log('Select a Project Folder first.'); return
        self.invalidate(); self.status.set('Scanning and checking project inputs...'); self.append_log('Scanning: '+folder)
        self.run('scan',lambda:scan_projects(folder,recursive))

    def start_generate(self,selected):
        if not self.scan or self.busy:return
        ids={self.scan['projects'][int(i)]['project_id'] for i in self.table.selection()} if selected else None
        if selected and not ids:return
        snapshot=self.scan; self.status.set('Generating...')
        self.run('generated',lambda:generate_batch(snapshot,ids,lambda event:self.events.put(('progress',event))))

    def details(self,*_):
        if self.scan and self.table.selection():self.append_log(project_details(self.scan['projects'][int(self.table.selection()[0])]))
        self.buttons()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    row=value['row']
                    for index,old in enumerate(self.scan['projects']):
                        if old['project_id']==row['project_id']:
                            self.scan['projects'][index]=row; self.table.item(str(index),values=self.row_values(row)); break
                    if value['event']=='started':self.append_log('[%d/%d] %s\nRechecking files, metadata and InstancePlan...' % (value['index'],value['total'],row['project_id']))
                    elif value['event']=='preflight':self.append_log('Preflight complete. Generating Assembly Script and Summary...')
                    elif value['event'] in ('finished','skipped'):self.append_log(project_details(row))
                    continue
                self.busy=False; self.progress.stop()
                if kind=='error':self.append_log('ERROR: '+value); self.status.set('Failed. See Process Log.')
                else:
                    selection=self.table.selection(); self.scan=value; self.table.delete(*self.table.get_children())
                    for index,row in enumerate(value['projects']):self.table.insert('','end',iid=str(index),values=self.row_values(row))
                    for item in selection:
                        if self.table.exists(item):self.table.selection_set(item)
                    if kind=='scan':
                        ready=sum(can_generate(r) for r in value['projects'])
                        message='Found %d projects | Ready %d | Blocked %d' % (len(value['projects']),ready,len(value['projects'])-ready)
                        self.status.set(message); self.append_log(message)
                        for row in value['projects']:self.append_log(row['project_id']+': '+row['input_status']+' — '+row['result'])
                    else:
                        message='Total %(total)d | Success %(success)d | Warning %(warning)d | Failed %(failed)d | Skipped %(skipped)d' % value['generation_counts']
                        self.status.set(message); self.append_log(message+'\nSuccess = generated without warnings; Warning = generated with warnings.')
                self.buttons()
        except queue.Empty:pass
        self.after(100,self.poll)

    def close(self):
        if self.busy:self.append_log('Please wait for the current operation to finish before closing.')
        else:self.destroy()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scan',help='Read-only folder scan for development/CLI checks')
    parser.add_argument('--include-subfolders',action='store_true')
    parser.add_argument('--scan-report',help='Optional JSON destination for --scan')
    parser.add_argument('--ui-smoke',action='store_true')
    args=parser.parse_args()
    if args.scan:
        result=json.dumps(scan_projects(args.scan,args.include_subfolders),ensure_ascii=False,indent=2)
        if args.scan_report:Path(args.scan_report).write_text(result,encoding='utf-8')
        if sys.stdout:print(result)
        return
    app=Step04AssemblyScriptApp()
    if args.ui_smoke:app.after(700,app.destroy)
    app.mainloop()

if __name__=='__main__':main()
