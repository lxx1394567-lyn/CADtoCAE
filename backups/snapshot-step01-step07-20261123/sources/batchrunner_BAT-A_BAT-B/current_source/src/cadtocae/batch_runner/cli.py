import argparse
import json
import signal
from pathlib import Path
from .executor import AbaqusExecutor
from .runner import BatchRunner
from .state import write_json

def main(argv=None):
    parser = argparse.ArgumentParser(description='CADtoCAE isolated serial Abaqus BatchRunner')
    parser.add_argument('mode', choices=['scan', 'smart', 'full', 'resume', 'from', 'migration-plan', 'migration-apply'])
    parser.add_argument('root')
    parser.add_argument('--output', help='Default: <root>/.batchrunner')
    parser.add_argument('--start', type=int, choices=range(1, 10), default=1)
    parser.add_argument('--config', help='JSON with command argv array and environment dictionary')
    parser.add_argument('--project', action='append', help='Project key returned by scan; repeatable')
    parser.add_argument('--stop-on-error', action='store_true')
    parser.add_argument('--plan', help='Reviewed internal migration plan path')
    parser.add_argument('--confirm-migration', action='store_true', help='Explicitly confirm listed legacy file migration')
    parser.add_argument('--through', type=int, choices=range(1,10), default=9, help='Last stage to execute (default 9)')
    args = parser.parse_args(argv)
    args.output = args.output or str(Path(args.root)/'.batchrunner')
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig')) if args.config else {}
    executor = AbaqusExecutor(config.get('command', ['abaqus']), config.get('environment'))
    if args.mode.startswith('migration-'):
        from .migration import plan_migration, apply_migration
        if args.mode == 'migration-plan':
            path, plan = plan_migration(args.root)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            print('Plan:', path)
        else:
            if not args.plan:
                parser.error('--plan is required')
            plan_data = json.loads(Path(args.plan).read_text(encoding='utf-8'))
            if Path(plan_data['root']).resolve() != Path(args.root).resolve():
                parser.error('Plan root differs from selected root')
            print(json.dumps(apply_migration(args.plan, executor, args.confirm_migration), ensure_ascii=False, indent=2))
        return 0
    runner = BatchRunner(args.root, args.output, executor, lambda p: print(p['prefix'], [(s['number'], s.get('action', ''), s['status']) for s in p['stages']], flush=True), through=args.through)
    if args.mode == 'scan':
        projects = [p.to_dict() for p in runner.inspect()]
        write_json(Path(args.output)/'scan.json', projects)
        print(json.dumps(projects, ensure_ascii=False, indent=2))
        return 0
    signal.signal(signal.SIGINT, lambda *_: (runner.stop.set(), print('Safe stop requested; waiting for current CAE stage to finish.')))
    directory, records = runner.run(args.mode, args.start, args.project, not args.stop_on_error)
    print('Report:', directory)
    for record in records:
        delivery = record.get('delivery', {})
        print(record['prefix'], 'execution='+record.get('execution_result', ''), 'delivery='+delivery.get('status', ''), 'model='+str(delivery.get('path') or ''))
    return 1 if any(p['result'] in ('FAILED', 'BLOCKED', 'DELIVERY_FAILED', 'NOT_VERIFIED') for p in records) else 0

if __name__ == '__main__':
    raise SystemExit(main())
