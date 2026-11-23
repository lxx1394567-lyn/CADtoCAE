"""Isolated executable entry. Normal UI generates scripts, never runs Abaqus."""
import argparse,json,sys,traceback
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--workbook');p.add_argument('--summary');p.add_argument('--holes');p.add_argument('--output');p.add_argument('--result');p.add_argument('--smoke-test',action='store_true');a=p.parse_args()
 if a.smoke_test:
  import tkinter as tk
  root=tk.Tk();root.withdraw();root.update_idletasks();root.destroy()
  result={'status':'SUCCESS','tk_hidden_start':'PASS','version':'V3-D1-1.1','abaqus_started':False}
 elif a.workbook:
  from cadtocae.step07_v3_load import v3_values,v3_calculate
  v,_=v3_values(a.workbook);result=v3_calculate(v)
  if a.summary:
   from cadtocae.step07_inplace import generate_inplace
   result['generated']=generate_inplace(a.summary,a.output,a.holes,stage=5,load_workbook=a.workbook,overwrite=False)
 else:
  from cadtocae.step07_pipeline_desktop import PipelineApp
  PipelineApp().mainloop();return
 if a.result:
  from cadtocae.step07_v3_guard import protect_output
  protect_output(a.result);Path(a.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':
 try:main()
 except Exception:
  if '--result' in sys.argv:
   from cadtocae.step07_v3_guard import protect_output
   dest=sys.argv[sys.argv.index('--result')+1];protect_output(dest);Path(dest).write_text(json.dumps({'status':'FAILED','error':traceback.format_exc()},indent=2),encoding='utf8')
  raise
