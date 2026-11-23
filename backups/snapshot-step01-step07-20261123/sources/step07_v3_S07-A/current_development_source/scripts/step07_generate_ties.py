import argparse,json
from cadtocae.step07_tie_setup import generate_tie_setup
p=argparse.ArgumentParser();p.add_argument('--summary',required=True);p.add_argument('--input-cae',required=True);p.add_argument('--output',required=True);a=p.parse_args()
print(json.dumps(generate_tie_setup(a.summary,a.input_cae,a.output),indent=2))
