import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.step07_pipeline import generate_pipeline
p=argparse.ArgumentParser();p.add_argument('--summary',required=True);p.add_argument('--input-cae',required=True);p.add_argument('--output',required=True);p.add_argument('--hole-report',required=True);p.add_argument('--stage',type=int,default=0);p.add_argument('--predecessor-report')
a=p.parse_args();print(json.dumps(generate_pipeline(a.summary,a.input_cae,a.output,a.hole_report,a.stage,a.predecessor_report),indent=2))
