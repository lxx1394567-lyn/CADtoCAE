"""Generate a self-contained Stage 2 script; never launch Abaqus automatically."""
import argparse
import json
from cadtocae.step07_bc_setup import generate_stage2

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--summary',required=True)
    parser.add_argument('--accepted-cae',required=True,help='Explicitly selected, human-accepted Stage 1 CAE')
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=('CURRENT_SESSION_DEBUG','INDEPENDENT_CAE'),default='CURRENT_SESSION_DEBUG')
    parser.add_argument('--p01-only',action='store_true')
    args=parser.parse_args()
    result=generate_stage2(args.summary,args.accepted_cae,args.output,args.mode,('P01',) if args.p01_only else ('P01','P02','P03','P04'))
    print(json.dumps(result,indent=2))
