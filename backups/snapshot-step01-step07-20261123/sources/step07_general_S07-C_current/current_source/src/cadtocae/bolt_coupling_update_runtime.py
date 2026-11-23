"""Update existing Step06 bolt couplings only. Python 2.7 compatible."""
import json
from .purlin_bolt_preset_runtime import resolve_step06_model


def bolt_coupling_names():
    names=[]
    for group in ('P01','P02','P03','P04'):
        for side in ('SUPPORT','PURLIN','SUPPORT_BEAM','BEAM'):
            names.append('STEP06_COUPLING_'+group+'_'+side)
    return names


def update_bolt_couplings(mdb,report_path,project_id):
    from abaqusConstants import ON, OFF, KINEMATIC
    import interaction
    names=bolt_coupling_names()
    report=dict(status='FAILED',expected_couplings=16,updated_couplings=0,errors=[],couplings=[])
    originals=[];attempted=[]
    fields=('couplingType','u1','u2','u3','ur1','ur2','ur3')
    try:
        model=resolve_step06_model(mdb,project_id)
        # Read and validate every target before touching any of them.
        for name in names:
            if name not in model.constraints.keys():raise ValueError('Missing bolt coupling: '+name)
            obj=model.constraints[name]
            if obj.suppressed:raise ValueError('Suppressed bolt coupling: '+name)
            values={}
            for field in fields:values[field]=getattr(obj,field)
            originals.append((obj,values,str(obj.controlPoint),str(obj.surface)))
        target=dict(couplingType=KINEMATIC,u1=ON,u2=ON,u3=ON,ur1=OFF,ur2=OFF,ur3=OFF)
        for obj,values,control,surface in originals:
            attempted.append((obj,values))
            obj.setValues(**target)
        for name,record in zip(names,originals):
            obj,values,control,surface=record
            for field in fields:
                if getattr(obj,field)!=target[field]:raise ValueError('Coupling verification failed: '+name)
            if str(obj.controlPoint)!=control or str(obj.surface)!=surface:
                raise ValueError('Coupling region binding changed: '+name)
            report['couplings'].append(dict(name=name,type='KINEMATIC',enabled=['U1','U2','U3'],disabled=['UR1','UR2','UR3']))
        report.update(status='SUCCESS',updated_couplings=16)
    except Exception as exc:
        report['errors'].append(str(exc))
        if attempted:
            try:
                for obj,values in reversed(attempted):obj.setValues(**values)
                report['rollback_status']='PASS'
            except Exception as rollback:
                report['rollback_status']='FAILED';report['errors'].append(str(rollback))
        raise
    finally:
        with open(report_path,'w') as handle:json.dump(report,handle,indent=2,ensure_ascii=True)
    return report
