"""Step05 development GUI; single Project Folder for inputs and outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import sys
import threading
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, messagebox, ttk

sys.dont_write_bytecode=True
if not getattr(sys,'frozen',False): sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.analysis_discovery import scan_projects
from cadtocae.analysis_batch import generate_batch
from cadtocae.analysis_capability import first_blocking_reason


class Step05App(Tk):
    def __init__(self):
        super().__init__()
        self.title('CADtoCAE Step05 v1.3 — Single Folder / Built-in Rules')
        self.geometry('1280x780');self.minsize(980,640)
        self.folder=StringVar();self.recursive=BooleanVar(value=False)
        self.status=StringVar(value='Select a Project Folder, then Scan Projects.')
        self.events=queue.Queue();self.busy=False;self.scan=None
        top=ttk.Frame(self,padding=12);top.pack(fill='x')
        top.columnconfigure(1,weight=1)
        self.inputs=[]
        ttk.Label(top,text='Project Folder').grid(row=0,column=0,sticky='w',pady=4)
        entry=ttk.Entry(top,textvariable=self.folder);entry.grid(row=0,column=1,sticky='ew',padx=10)
        button=ttk.Button(top,text='Select Folder',command=lambda:self.choose(self.folder));button.grid(row=0,column=2)
        self.inputs.extend([entry,button])
        check=ttk.Checkbutton(top,text='Include Subfolders (default OFF)',variable=self.recursive)
        check.grid(row=1,column=1,sticky='w');self.inputs.append(check)
        self.scan_button=ttk.Button(top,text='Scan Projects',command=self.start_scan)
        self.scan_button.grid(row=1,column=2,pady=8)
        columns=('project','structure','status','capability','generation','result')
        self.table=ttk.Treeview(self,columns=columns,show='headings',selectmode='extended',height=12)
        for key,label,width in zip(columns,('Project ID','Structure','Input','Capability','Generation','Result'),(360,80,130,90,130,300)):
            self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=70,stretch=False)
        self.table.pack(fill='both',expand=True,padx=12)
        scroll=ttk.Scrollbar(self,orient='horizontal',command=self.table.xview);scroll.pack(fill='x',padx=12)
        self.table.configure(xscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',self.details)
        self.log=Text(self,height=12,wrap='word',state='disabled');self.log.pack(fill='both',padx=12,pady=8)
        bottom=ttk.Frame(self,padding=12);bottom.pack(fill='x')
        self.selected=ttk.Button(bottom,text='Generate Selected',command=lambda:self.start_generate(True));self.selected.pack(side='left')
        self.all_ready=ttk.Button(bottom,text='Generate All Ready',command=lambda:self.start_generate(False));self.all_ready.pack(side='left',padx=10)
        ttk.Label(bottom,textvariable=self.status).pack(side='left',padx=6)
        for var in (self.folder,self.recursive):var.trace_add('write',self.invalidate)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.append_log('Step05 v1.3 | Single Project Folder | Built-in SP_SC / SP_DC rules')
        self.append_log('Executable: '+sys.executable)
        self.buttons();self.after(100,self.poll)

    def choose(self,var):
        value=filedialog.askdirectory(parent=self)
        if value:var.set(value)

    def invalidate(self,*_):
        self.scan=None;self.table.delete(*self.table.get_children());self.buttons()

    def buttons(self):
        available=self.scan is not None and not self.busy
        ready=bool(self.scan and any(self.can_generate(r) for r in self.scan['projects']))
        selected_ready=available and any(self.can_generate(self.scan['projects'][int(i)]) for i in self.table.selection())
        self.all_ready.configure(state='normal' if available and ready else 'disabled')
        self.selected.configure(state='normal' if selected_ready else 'disabled')
        self.scan_button.configure(state='disabled' if self.busy else 'normal')
        for widget in self.inputs:widget.configure(state='disabled' if self.busy else 'normal')

    def append_log(self,text):
        self.log.configure(state='normal');self.log.insert('end',text+'\n');self.log.see('end');self.log.configure(state='disabled')

    @staticmethod
    def can_generate(row):
        return row.get('input_status')=='READY' and row.get('capability') in ('SP_SC_FULL_CONNECTION_SETUP','SP_DC_FULL_CONNECTION_SETUP')

    def row_values(self,r):
        capability='FULL' if r['capability'] in ('SP_SC_FULL_CONNECTION_SETUP','SP_DC_FULL_CONNECTION_SETUP') else (r['capability'] or '')
        result=r.get('result') or ('Outputs found' if r['generation_status']=='GENERATED' else '')
        return (r['project_id'],r['structure_type'] or 'UNKNOWN',r['input_status'],capability,r['generation_status'],result)

    def completion_text(self,counts):
        heading='Step05 generation completed with errors.' if counts['failed'] else 'Step05 generation completed.'
        return heading+'\n\nSucceeded: %d\nFailed: %d\n\nOutput folder:\n%s' % (counts['succeeded'],counts['failed'],self.folder.get())+('\n\nSee log for details.' if counts['failed'] else '')

    def show_completion(self,counts):
        notify=messagebox.showwarning if counts['failed'] else messagebox.showinfo
        notify('Step05 generation',self.completion_text(counts),parent=self)

    def run(self,operation):
        self.busy=True;self.buttons()
        def work():
            try:self.events.put(('done',operation()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def start_scan(self):
        folder=self.folder.get();recursive=self.recursive.get()
        if not folder:messagebox.showerror('Project Folder required','Please select a project folder.');return
        self.scan=None;self.table.delete(*self.table.get_children())
        self.operation='scan';self.status.set('Scanning folder...');self.append_log('Scanning folder: '+folder)
        self.run(lambda:scan_projects(folder,recursive))

    def start_generate(self,selected):
        if not self.scan:return
        selection={(self.scan['projects'][int(i)]['source_folder'],self.scan['projects'][int(i)]['project_id']) for i in self.table.selection()} if selected else None
        scan=self.scan;self.operation='generate'
        self.status.set('Generating...');self.append_log('Generate Selected:' if selected else 'Generate All Ready:')
        self.run(lambda:generate_batch(scan,selection,lambda event:self.events.put(('progress',event))))

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    row=value['row']
                    for i,old in enumerate(self.scan['projects']):
                        if (old['source_folder'],old['project_id'])==(row['source_folder'],row['project_id']):
                            self.scan['projects'][i]=row;self.table.item(str(i),values=self.row_values(row));break
                    if value['event']=='skipped':
                        self.append_log(row['project_id']+' skipped: '+row['skip_reason']);continue
                    if value['event']=='started':self.append_log('[%d/%d] %s' % (value['index'],value['total'],row['project_id']))
                    else:
                        if row['generation_status']=='GENERATED':
                            self.append_log('  AnalysisPlan generated\n  Abaqus script generated\n  SUCCESS')
                        else:self.append_log('  FAILED: '+'; '.join(row['errors'])+'\n'+row.get('traceback',''))
                    self.status.set(row['project_id']+': '+row['generation_status']);continue
                self.busy=False
                if kind=='error':
                    self.append_log('ERROR: '+value);messagebox.showerror('Step05',value);self.status.set(value)
                else:
                    self.scan=value
                    selection=self.table.selection();self.table.delete(*self.table.get_children())
                    for i,row in enumerate(value['projects']):self.table.insert('','end',iid=str(i),values=self.row_values(row))
                    for iid in selection:
                        if self.table.exists(iid):self.table.selection_add(iid)
                    if self.operation=='scan':
                        self.append_log('Found %d projects.' % len(value['projects']))
                        for row in value['projects']:self.append_log(row['project_id']+'\n  '+row['input_status']+' / '+row['generation_status'])
                        self.status.set('Scan completed. Select projects or Generate All Ready.')
                    else:
                        counts=value['generation_counts']
                        text='Generation completed\nSucceeded: %d\nFailed: %d' % (counts['succeeded'],counts['failed'])
                        self.append_log(text);self.status.set('Succeeded: %d | Failed: %d' % (counts['succeeded'],counts['failed']))
                        self.buttons();self.show_completion(counts)
                self.buttons()
        except queue.Empty:pass
        self.after(100,self.poll)

    @staticmethod
    def project_details(row):
        lines=[row['project_id'],'Status: '+row.get('input_status',row.get('status','UNKNOWN')),
               'Capability: '+str(row.get('capability') or 'not confirmed'),
               'Supported Rules: '+(', '.join(row.get('supported_rules',[])) or 'none confirmed'),
               'Missing Requirements:']
        missing=[]
        for category,values in row.get('missing_requirements',{}).items():
            for value in values:missing.append('  '+category+': '+str(value))
        lines.extend(missing or ['  None'])
        lines.append('Warnings:')
        lines.extend(row.get('warnings') or ['  None'])
        lines.append('First Blocking Reason: '+(first_blocking_reason(row) or 'None'))
        if row.get('geometry_review'):
            lines.append('Expected nominal Tie count: '+str(row.get('expected_nominal_tie_count','not confirmed')))
            lines.append('Executable Tie count: not confirmed')
        elif 'expected_tie_count' in row:
            lines.append('Expected Tie count: '+str(row['expected_tie_count']))
        if row.get('hoop_component_mappings'):
            lines.append('HOOP component mappings:')
            for m in row['hoop_component_mappings']:
                lines.append('  %s: raw=%s; component record=%s; canonical=%s; Part=%s' %
                    (m['instance_name'],m['raw_component_code'],m['component_record_code'],m['canonical_role'],m['part_name']))
        return '\n'.join(lines)

    def details(self,*_):
        if self.scan and self.table.selection():
            row=self.scan['projects'][int(self.table.selection()[0])]
            self.append_log(self.project_details(row))
        self.buttons()

    def close(self):
        if self.busy:messagebox.showinfo('Step05','Please wait until the current operation finishes.');return
        self.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scan',metavar='PROJECT_FOLDER',help='Headless read-only scan for development verification')
    parser.add_argument('--generate',action='store_true')
    parser.add_argument('--ui-validate',metavar='PROJECT_FOLDER',help='Development smoke: exercise GUI Scan and Generate All Ready')
    parser.add_argument('--include-subfolders',action='store_true')
    parser.add_argument('--ui-smoke',action='store_true',help='Create the GUI and exit after its first event loop')
    args=parser.parse_args()
    if args.scan:
        result=scan_projects(args.scan,args.include_subfolders)
        if args.generate:result=generate_batch(result)
        if sys.stdout:print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if any(r['generation_status']=='FAILED' for r in result['projects']) else 0
    app=Step05App()
    result=[0]
    if args.ui_smoke:app.after(500,app.destroy)
    if args.ui_validate:
        app.folder.set(args.ui_validate)
        # Unattended smoke records the notification without waiting for OK.
        app.show_completion=lambda counts:app.append_log(app.completion_text(counts))
        phase=[0]
        def validate_ui():
            if app.busy:app.after(100,validate_ui);return
            if phase[0]==0:
                phase[0]=1;app.start_scan()
            elif phase[0]==1:
                if not app.scan or str(app.all_ready['state'])!='normal':result[0]=1;app.destroy();return
                phase[0]=2;app.start_generate(False)
            else:
                result[0]=int(not app.scan or app.scan.get('generation_counts',{}).get('failed',1)!=0)
                app.destroy();return
            app.after(100,validate_ui)
        app.after(100,validate_ui)
    app.mainloop();return result[0]


if __name__=='__main__':raise SystemExit(main())
