"""Generate only; independent mode is available for regression callers."""
import argparse,json
from cadtocae.step07_mesh_setup import generate_stage3
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--summary',required=True)
    parser.add_argument('--accepted-cae',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=('CURRENT_SESSION_DEBUG','INDEPENDENT_CAE'),default='CURRENT_SESSION_DEBUG')
    args=parser.parse_args()
    result=generate_stage3(args.summary,args.accepted_cae,args.output,args.mode)
    print(result['script'])
