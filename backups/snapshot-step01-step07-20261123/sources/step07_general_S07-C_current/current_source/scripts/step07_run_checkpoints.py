"""Optional sequential runner. No Job submission; stops on a failed stage report."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--abaqus',required=True);p.add_argument('--through',type=int,choices=(1,2,3,4),default=4)
a=p.parse_args();manifest=json.loads(Path(a.manifest).read_text(encoding='utf-8-sig'))
for c in manifest['stages']:
 if c['stage']>a.through:break
 print('STAGE',c['stage'],c['script'],flush=True)
 subprocess.run([a.abaqus,'cae','noGUI='+c['script']],check=True,cwd=str(Path(a.manifest).parent))
 path=Path(c['report_path'])
 if not path.exists():raise RuntimeError('Abaqus returned without a stage report')
 report=json.loads(path.read_text(encoding='utf-8-sig'))
 if report.get('status')!='SUCCESS':raise RuntimeError('Stage failed: '+str(path))
 print('SUCCESS',c['output_cae'],flush=True)
print('Stopped before load stage; waiting for user load data.')
