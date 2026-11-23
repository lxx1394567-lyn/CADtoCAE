"""Generate P01-P04 connectors from an existing SUCCESS Step06-A report."""
import argparse
from cadtocae.connector_setup import generate_connector_setup

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(generate_connector_setup(args.plan,args.report,args.output))
