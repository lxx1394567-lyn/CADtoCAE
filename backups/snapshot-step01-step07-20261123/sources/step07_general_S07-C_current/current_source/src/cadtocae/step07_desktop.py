"""Desktop orchestration only; all analysis operations use step07_setup/runtime."""
import copy
from datetime import datetime
import hashlib
import json
import locale
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from .step07_setup import build_plan, generate

VERSION='0.1.0'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inspect_summary(path):
    s=read_json(path)
    roles=('COLUMN_FRONT','COLUMN_REAR') if s['structure_type']=='DP' else ('COLUMN_DOWN',)
    bottoms=[r['instance_name'] for r in s['instances'] if r['canonical_role'] in roles]
    purlins=[dict(instance=r['instance_name'],rp_set='STEP06_RP_'+str(r.get('connection_group'))+'_PURLIN') for r in s['instances'] if r['canonical_role'] in ('PURLIN','PURLIN_LOCAL')]
    candidate=Path(path).with_name(s['project_id']+'_analysis_plan.json')
    return dict(summary=s,bottoms=bottoms,purlins=purlins,connection_plan=str(candidate) if candidate.is_file() else '')


def load_configuration(path):
    c=read_json(path)
    for name in ('input_cae','connection_plan','assembly_summary','output_folder'):
        if c.get(name) and not Path(c[name]).is_absolute():c[name]=str((Path(path).resolve().parent/c[name]).resolve())
    return c


def new_run(config,summary_path,output_folder):
    source=Path(config['input_cae']).resolve(strict=True)
    summary_path=Path(summary_path).resolve(strict=True)
    if source.suffix.lower()!='.cae':raise ValueError('输入文件必须为 .cae')
    s=read_json(summary_path)
    c=copy.deepcopy(config);c['input_cae']=str(source)
    c.setdefault('job',{})['submit']=False
    c=build_plan(c,s)
    base=Path(output_folder).resolve();base.mkdir(parents=True,exist_ok=True)
    run=base/('Step07_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);run.mkdir()
    config_file=run/'step07_config.json'
    config_file.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(summary_path,run/'assembly_summary.json')
    if c.get('connection_plan'):shutil.copy2(c['connection_plan'],run/'connection_plan.json')
    script=generate(config_file,summary_path,run)
    (run/'desktop_run.json').write_text(json.dumps(dict(version=VERSION,input_cae=str(source),summary=str(summary_path),script=str(script),status='GENERATED',automatic_submit=False),ensure_ascii=False,indent=2),encoding='utf-8')
    return run


def abaqus_command(value):
    path=Path(value.strip().strip('"')) if value.strip() else Path(shutil.which('abaqus') or '')
    if not path.is_file() or path.suffix.lower() not in ('.bat','.exe','.cmd'):
        raise ValueError('找不到 ABAQUS 命令，请指定安装目录 Commands 中的 abaqus.bat')
    if any(c in str(path) for c in '&|<>^%!\r\n"'):raise ValueError('ABAQUS 启动路径含不支持的命令字符')
    return str(path.resolve())


def execute(run,command,operation,emit=lambda text:None,stage_plan=None):
    run=Path(run).resolve()
    if operation not in ('setup','submit'):raise ValueError('Unknown operation')
    script='step07_analysis_setup.py' if operation=='setup' else 'step07_submit_job.py'
    if operation=='setup' and (run/'step07_plan.json').exists():
        plan=read_json(run/'step07_plan.json')
        if plan.get('stage')==1:
            script=plan.get('script_name',script)
            if Path(script).name!=script or not script.endswith('.py'):raise ValueError('Invalid stage script name')
    if stage_plan is not None:script=stage_plan['script_name']
    if not (run/script).is_file():raise ValueError('找不到生成脚本：'+script)
    if stage_plan is not None:
        if operation!='setup' or stage_plan.get('stage')!=1:raise ValueError('Invalid stage operation')
        if stage_plan.get('execution_mode','INDEPENDENT_CAE')!='INDEPENDENT_CAE':raise ValueError('Automatic execution requires an INDEPENDENT_CAE script; regenerate using automatic mode')
        script=stage_plan['script_name']
        if Path(script).name!=script or not (run/script).is_file():raise ValueError('Invalid stage script')
        for key in ('output_cae','report_path','log_path','console_log','scratch_cae'):
            if Path(stage_plan[key]).exists():raise ValueError('Output exists; regenerate version: '+stage_plan[key])
    old_locator=None
    if operation=='submit':
        r=read_json(run/'step07_report.json')
        if r['status'] not in ('SETUP_COMPLETE','VERIFIED','VERIFIED_WORKFLOW_ONLY'):raise ValueError('分析设置尚未成功，不能提交')
        locator=run/'step07_last_submission.json'
        old_locator=locator.read_bytes() if locator.exists() else None
        if locator.exists() and read_json(locator).get('status')=='RUNNING':raise ValueError('已有求解仍在运行，不能重复提交')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    logfile=Path(stage_plan['console_log']) if stage_plan else run/(operation+'_'+stamp+'.log')
    argv=[abaqus_command(command),'cae','noGUI='+script]
    emit('运行：'+str(run/script));emit('日志：'+str(logfile))
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with logfile.open('xb' if stage_plan else 'wb') as log:
        process=subprocess.Popen(argv,cwd=str(run),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=flags)
        emit('ABAQUS 进程 PID：'+str(process.pid))
        for raw in iter(process.stdout.readline,b''):
            log.write(raw);log.flush()
            emit(raw.decode(locale.getpreferredencoding(False),errors='replace').rstrip())
        process.stdout.close();code=process.wait()
    if operation=='setup':report_path=Path(stage_plan['report_path']) if stage_plan else run/'step07_report.json'
    else:
        if not (run/'step07_last_submission.json').exists():raise RuntimeError('未生成提交报告。请查看 '+str(logfile))
        if (run/'step07_last_submission.json').read_bytes()==old_locator:raise RuntimeError('未生成本次提交结果，拒绝读取上次报告。日志：'+str(logfile))
        locator=read_json(run/'step07_last_submission.json')
        report_path=Path(locator.get('report_path',''))
    if not report_path.is_file():raise RuntimeError('ABAQUS 未生成完整报告（退出码 %s）。日志：%s'%(code,logfile))
    report=read_json(report_path)
    report['_report_path']=str(report_path);report['_console_log']=str(logfile)
    if report.get('status') not in ('SETUP_COMPLETE','VERIFIED','VERIFIED_WORKFLOW_ONLY'):
        raise RuntimeError(report.get('error','ABAQUS 执行失败')+'\n报告：'+str(report_path))
    if code!=0:raise RuntimeError('ABAQUS 退出码非零：%s；报告：%s'%(code,report_path))
    if operation=='setup' and not Path(report.get('cae',run/'step07.cae')).is_file():raise RuntimeError('报告成功但输出 CAE 不存在')
    return report
