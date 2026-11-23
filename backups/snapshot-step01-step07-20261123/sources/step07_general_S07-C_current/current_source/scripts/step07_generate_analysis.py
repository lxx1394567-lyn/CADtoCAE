"""Generate a self-contained Abaqus/CAE 2020 noGUI script."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.step07_setup import generate
p=argparse.ArgumentParser()
p.add_argument('config');p.add_argument('summary');p.add_argument('output')
a=p.parse_args()
print(generate(a.config,a.summary,a.output))
