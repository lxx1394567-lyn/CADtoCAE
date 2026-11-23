import argparse
from cadtocae.support_beam_connector import generate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Generate independent Support-Beam connector script')
    parser.add_argument('--folder',required=True)
    parser.add_argument('--project',required=True)
    args=parser.parse_args()
    print(generate(args.folder,args.project))
