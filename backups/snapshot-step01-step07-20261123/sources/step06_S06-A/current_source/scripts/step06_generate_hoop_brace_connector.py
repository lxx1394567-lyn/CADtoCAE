"""Generate the standalone SP_SC ANG18 HOOP A / BRACE connector script."""
import argparse
from cadtocae.hoop_brace_setup import generate_hoop_brace
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',required=True)
    parser.add_argument('--project',required=True)
    args=parser.parse_args()
    print(generate_hoop_brace(args.folder,args.project))
