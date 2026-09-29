"""Generate BEAM_BRACE_TIE setup; explicit legacy modes retain A2 experiments."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cadtocae.analysis_setup import generate_analysis_setup
from cadtocae.analysis_project import discover_project_folder, explicit_project_files, generate_real_analysis_setup
from cadtocae.beam_brace_tie import generate as generate_beam_brace_tie


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-folder", help="Discover a real case in this directory (nonrecursive)")
    parser.add_argument("--legacy-a2", action="store_true", help="Explicit historical geometry-only validation mode")
    parser.add_argument("--components")
    parser.add_argument("--coordinate")
    parser.add_argument("--assembly-summary")
    parser.add_argument("--part-script", help="Existence/name check only; never parsed")
    parser.add_argument("--assembly-script", help="Existence/name check only; never parsed")
    parser.add_argument("--summary", help="Legacy explicit analysis-input mode")
    parser.add_argument("--analysis", help="Tie_Config analysis.xlsx for real mode; legacy input with --summary")
    parser.add_argument("--output-dir", help="Real-case default: <case>/step05_validation")
    args = parser.parse_args()
    try:
        files = None
        if args.project_folder:
            if any((args.components, args.coordinate, args.assembly_summary, args.part_script, args.assembly_script, args.summary)):
                parser.error("--project-folder cannot be combined with explicit input files")
            files = discover_project_folder(args.project_folder)
        elif any((args.components, args.coordinate, args.assembly_summary, args.part_script, args.assembly_script)):
            if not all((args.components, args.coordinate, args.assembly_summary)) or args.summary:
                parser.error("Explicit real mode requires --components --coordinate --assembly-summary; no legacy inputs")
            files = explicit_project_files(args.components, args.coordinate, args.assembly_summary, args.part_script, args.assembly_script)
        elif not all((args.summary, args.analysis, args.output_dir)):
            parser.error("Use --project-folder, explicit real files, or --summary --analysis --output-dir")
        if files:
            if args.legacy_a2 and args.analysis:
                parser.error("--legacy-a2 uses its historical fixed input; omit --analysis")
            results = (generate_real_analysis_setup(files, args.output_dir) if args.legacy_a2 else
                       generate_beam_brace_tie(files, args.analysis, args.output_dir))
            print("STEP05 REAL CASE: generation only, runtime geometry validation pending")
            for name, path in files.paths().items():
                print("%s: %s" % (name, path))
            print("In the same Abaqus/CAE model, run in order:")
            for index, path in enumerate((files.part_script, files.assembly_script, results["script"]), 1):
                print("%d. %s" % (index, path))
        else:
            results = generate_analysis_setup(args.summary, args.analysis, args.output_dir)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, "Step05 preflight failed: %s\n" % exc)
    for name, path in results.items():
        print("%s: %s" % (name, path))
    print("runtime_report is written only when the script is run in Abaqus/CAE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
