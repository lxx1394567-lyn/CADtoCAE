"""DP fixtures and native-geometry contract tests; no private inputs required."""
import copy
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from openpyxl import load_workbook

import test_analysis_beam_brace_tie as bb
import test_analysis_column_column_tie as cc
import test_analysis_column_hoop_tie as hh
from analysis_fake_cae import Repository
from cadtocae.analysis_discovery import scan_projects,project_files
from cadtocae.analysis_batch import generate_batch
from cadtocae.dp_rules import build_dp_plan,default_dp_config,dp_requirements,selected_components
from cadtocae.dp_setup import generate
from cadtocae.column_beam_coupling import resolve_face_coupling
from cadtocae.column_hoop_tie import resolve_hoop
from cadtocae.runtime_compatibility import assert_runtime_compatible

ROOT=Path(__file__).resolve().parents[1]


class DPPlannerTests(unittest.TestCase):
    def setUp(self):
        self.base=bb.PlannerTests();self.addCleanup(self.base.doCleanups);self.base.setUp()
        s=self.base.summary;s['structure_type']='DP';s['warnings']=['ANG14 rear column length diagnostic']
        s['instances'][0]['placement']=dict(translation=[0,0,.1],axis_direction=[1,0,0],rotation_steps=[])
        s['hoop_groups']=[]
        for i,(role,x) in enumerate((('COLUMN_FRONT',.4),('COLUMN_REAR',1.3)),1):
            instance=role+'_01'
            s['instances'].append(dict(canonical_role=role,component_code=role,instance_name=instance,part_name='P_'+role,
                geometry_info=dict(length=1.6,section_kind='PIPE'),placement=dict(translation=[x,0,-1.5],rotation_steps=[])))
            prefix='CF' if i==1 else 'CR'
            s['assembly_points'][prefix+'0']=[x,0,-1.5];s['assembly_points'][prefix+'1']=[x,0,.15]  # diagnostic only
            gid='HOOP_%02d'%i
            for label in ('A','B'):
                s['instances'].append(dict(component_code='HOOP',canonical_role='HOOP',part_name='P_HOOP',
                    instance_name=gid+'_'+label,connection_group=gid,geometry_info=dict(length=None,section_kind='HOOP_BAND'),
                    placement=dict(translation=[x,0,-.24],rotation_steps=[],rotation_angle=0 if label=='A' else 180,rotation_axis=[0,0,1])))
            s['hoop_groups'].append(dict(group_id=gid,column_instance=instance,instance_a=gid+'_A',instance_b=gid+'_B'))
        self.base.write_summary()
        w=load_workbook(self.base.components)
        for role,label in (('COLUMN_FRONT','前立柱'),('COLUMN_REAR','后立柱')):
            w.active.append(['双桩双立柱',14,label,'φ177×4',1600,1,'Q355B','SHELL','S4R','P_'+role,'已确认'])
        w.active.append(['双桩双立柱',14,'抱箍','HOOP(D=177,W=80,T=6,L=100,R=100,RF=6)',None,1,'Q355B','SOLID','C3D8R','P_HOOP','已确认'])
        w.save(self.base.components);w.close()
        w=load_workbook(self.base.coordinate)
        for k in ('CF0','CF1','CR0','CR1'):w.active.append([k]+s['assembly_points'][k])
        w.save(self.base.coordinate);w.close()
        self.files=project_files(self.scan())

    def scan(self):return scan_projects(self.base.root)['projects'][0]
    def plan(self):return build_dp_plan(self.files)

    def test_capability_and_expected_counts(self):
        row=self.scan();self.assertEqual(row['input_status'],'READY',row['errors'])
        self.assertEqual(row['capability'],'DP_FULL_CONNECTION_SETUP')
        self.assertEqual((row['expected_tie_count'],row['expected_rp_count'],row['expected_coupling_count']),(6,2,4))

    def test_missing_roles(self):
        original=copy.deepcopy(self.base.summary)
        for role in ('INCLINED_BEAM','BRACE_FRONT','BRACE_REAR','COLUMN_FRONT','COLUMN_REAR'):
            self.base.summary=copy.deepcopy(original)
            self.base.summary['instances']=[m for m in original['instances'] if m.get('canonical_role')!=role]
            self.base.write_summary();row=self.scan()
            self.assertEqual(row['input_status'],'NEEDS_REVIEW');self.assertIn(role,str(row['missing_requirements']['roles']))

    def test_missing_control_points(self):
        for key in ('CF0','CF1','CR0','CR1'):
            value=self.base.summary['assembly_points'].pop(key);self.base.write_summary()
            self.assertIn(key,self.scan()['missing_requirements']['points'])
            self.base.summary['assembly_points'][key]=value

    def test_real_top_projection_not_control_points(self):
        for rule,station in zip(self.plan()['column_beam_couplings'],(.4,1.3)):
            self.assertAlmostEqual(rule['rp_coordinate'][2],.1)
            self.assertAlmostEqual(rule['station_m'],station)
            self.assertAlmostEqual(rule['control_point_diagnostic']['delta'][2],-.05)
            self.assertAlmostEqual(rule['beam_range'][0],station-.05)
            self.assertEqual(rule['column_region_mode'],'TOP_BAND_FACE')
            self.assertEqual(rule['beam_region_mode'],'WEB_PATCH_FACE')
            self.assertEqual(rule['column']['interval'],[1.55,1.6])

    def test_station_range_and_overlapping_patches(self):
        summary=self.base.summary
        for x,reason in ((.02,'outside beam'),(.4,'overlap')):
            next(m for m in summary['instances'] if m.get('canonical_role')=='COLUMN_REAR')['placement']['translation'][0]=x
            self.base.write_summary()
            with self.assertRaisesRegex(ValueError,reason):self.plan()

    def test_mapped_groups_and_names_no_single_pile_rules(self):
        p=self.plan();expected=p['expected_constraints']
        self.assertEqual(expected['tie_count'],6)
        self.assertNotIn('COLUMN_COLUMN_TIE',p['supported_rules']);self.assertNotIn('COLUMN_BEAM_TIE',p['supported_rules'])
        for group,role in zip(p['column_hoop_groups'],('COLUMN_FRONT','COLUMN_REAR')):
            self.assertEqual(group['column']['role'],role)
            for half in group['halves']:
                self.assertEqual(half['tie'],'STEP05_TIE_'+role+'_'+group['group_id']+'_'+half['label'])
        self.assertEqual(expected['rp_names'],['STEP05_RP_COLUMN_FRONT','STEP05_RP_COLUMN_REAR'])
        self.assertEqual(len(set(expected['coupling_names'])),4)
        self.assertNotIn('COLUMN_DOWN',json.dumps(p));self.assertNotIn('COLUMN_UP',json.dumps(p))
        self.assertEqual(p['warnings'],self.base.summary['warnings'])

    def test_mapping_is_explicit_not_group_number(self):
        s=self.base.summary
        for m in s['instances']:
            if m.get('connection_group')=='HOOP_01':m['connection_group']='FRONT_RING_90'
        s['hoop_groups'][0]['group_id']='FRONT_RING_90';self.base.write_summary()
        self.assertEqual(self.plan()['column_hoop_groups'][0]['column']['role'],'COLUMN_FRONT')
        del s['hoop_groups'][0]['column_instance'];self.base.write_summary()
        self.assertIn('column_instance',str(self.scan()['missing_requirements']))

    def test_incomplete_pair(self):
        self.base.summary['instances']=[m for m in self.base.summary['instances'] if m['instance_name']!='HOOP_02_B']
        self.base.write_summary();self.assertTrue(self.scan()['missing_requirements']['hoop_groups'])

    def test_unrelated_missing_thickness_is_ignored(self):
        from cadtocae import dp_rules
        rows=dp_rules.load_dimension_complete_components(self.files.components)
        rows += [dict(abaqus_part_name='P_MID_CLAMP'),dict(abaqus_part_name='P_EDGE_CLAMP')]
        with patch.object(dp_rules,'load_dimension_complete_components',return_value=rows):
            self.assertEqual(len(selected_components(self.files,self.base.summary)),6)
            self.assertEqual(self.plan()['expected_constraints']['tie_count'],6)

    def test_generation_python2_and_batch(self):
        from lib2to3.refactor import RefactoringTool
        paths=generate(self.files,output_dir=self.base.root/'generated')
        s=paths['script'].read_text(encoding='utf-8');assert_runtime_compatible(s)
        RefactoringTool([]).refactor_string(s+'\n','dp')
        self.assertNotIn('execute_sp_dc',s)
        result=generate_batch(scan_projects(self.base.root))
        self.assertEqual(result['generation_counts'],dict(succeeded=1,failed=0))

    def test_horizontal_hoop_flip_uses_final_origin(self):
        s=self.base.summary;meta=s['hoop_groups'][0]
        b=next(m for m in s['instances'] if m['instance_name']=='HOOP_01_B')
        rotation=dict(axis_point=[.4,0,-.2],axis_direction=[1,0,0],angle_deg=180.)
        b['placement']['rotation_steps']=[rotation]
        meta.update(pair_transform_rule='DP_ASYMMETRIC_HORIZONTAL_FLIP',pair_rotation=rotation)
        self.base.write_summary()
        group=self.plan()['column_hoop_groups'][0]
        self.assertAlmostEqual(group['halves'][1]['placement']['final_origin'][2],-.16)
        for a,b in zip(group['halves'][0]['expected_band'],group['halves'][1]['expected_band']):self.assertAlmostEqual(a,b)


class DPFaceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.base=bb.RuntimeTests();self.addCleanup(self.base.doCleanups);self.base.setUp()
        self.rt=self.base.runtime
        for name in ('column_axis.py','column_column_tie_runtime.py','column_hoop_tie_runtime.py',
                     'column_beam_coupling_runtime.py','tie_preflight_runtime.py','dp_runtime.py'):
            exec((ROOT/'src/cadtocae'/name).read_text(encoding='utf-8'),self.rt)
        self.model=self.base.model;self.a=self.model.rootAssembly
        self.a.features=Repository();self.a.referencePoints={}
        self.a.Set=lambda name,**kw:self.a.sets.update({name:NS(**kw)})
        def rp(point):
            index=100+len(self.a.referencePoints);self.a.referencePoints[index]=NS(coordinate=tuple(point))
            feature=NS(id=index,name='RP-auto');self.a.features[feature.name]=feature;return feature
        self.a.ReferencePoint=rp;self.a.getCoordinates=lambda entity:entity.coordinate
        self.model.Coupling=lambda **kw:self.model.constraints.update({kw['name']:NS(**kw)})
        summary=dict(instances=[]);components=[]
        for role,length,origin,kind in (('INCLINED_BEAM',2.,[0,0,0],'C_CHANNEL'),
                                        ('COLUMN_FRONT',1.6,[0,0,-1.35],'PIPE'),('COLUMN_REAR',1.6,[0,0,.15],'PIPE')):
            name='BEAM' if role=='INCLINED_BEAM' else role
            summary['instances'].append(dict(component_code=role,canonical_role=role,instance_name=name,part_name=name,
                geometry_info=dict(length=length,section_kind=kind),placement=dict(translation=origin,rotation_steps=[])))
            components.append(dict(component_code=role,part_name=name,section_kind=kind,model_policy='SHELL',length_m=length,
                thickness_m=.004,section_params_m=dict(od_m=.177,t_m=.004,h_m=.09,b_m=.05)))
        self.rules=[resolve_face_coupling(summary,components,role,default_dp_config()['COLUMN_BEAM_COUPLING'])
                    for role in ('COLUMN_FRONT','COLUMN_REAR')]
        self.summary,self.components=summary,components
        for rule in self.rules:
            pipe=hh.Pipe(rule['column']);self.model.parts[pipe.name]=pipe;self.a.instances[pipe.name]=hh.Instance(pipe)
        self.plan=dict(self.base.plan,column_beam_couplings=self.rules)

    def prepare(self):
        return [self.rt['prepare_face_coupling'](self.plan,r,self.base.mdb,str(self.base.report),'XYPLANE','ON') for r in self.rules]

    def finish(self,contexts):
        with contextlib.redirect_stdout(io.StringIO()):
            return [self.rt['execute_coupling'](c,'ON','OFF','DISTRIBUTING','WHOLE_SURFACE','UNIFORM') for c in contexts]

    def test_two_rps_four_couplings_repeat_and_web_only(self):
        contexts=self.prepare();reports=self.finish(contexts)
        self.assertEqual(len(self.a.referencePoints),2);self.assertEqual(len(self.model.constraints),4)
        for rule,report in zip(self.rules,reports):
            self.assertEqual(report['reference_point']['coordinate'],rule['rp_coordinate'])
            self.assertTrue(all(t['target_type']=='FACE' for t in report['targets']))
            cp=self.model.parts[rule['column']['part_name']]
            self.assertIn(1.55,cp.stations)
            beam=self.model.parts['BEAM']
            for index in report['targets'][1]['selected_ids']:
                self.assertTrue(all(abs(beam.vertices[i].pointOn[0][0])<1.e-6 for i in beam.faces[index].getVertices()))
            for coupling in report['couplings']:self.assertEqual(len(coupling['dofs']),6)
        before=(len(self.a.features),len(self.a.sets),len(self.a.surfaces),len(self.model.constraints))
        again=self.finish(self.prepare())
        self.assertEqual(before,(len(self.a.features),len(self.a.sets),len(self.a.surfaces),len(self.model.constraints)))
        self.assertTrue(all(not c['created'] for r in again for c in r['couplings']))

    def test_geometry_mismatch_before_partition(self):
        self.rules[0]['rp_coordinate'][2]+=.1
        with self.assertRaisesRegex(ValueError,'RP'):self.prepare()
        self.assertEqual(self.model.parts['BEAM'].mutations,[])

    def test_missing_web_and_incomplete_column_band(self):
        contexts=self.prepare()
        with patch.dict(self.rt,zone_faces=lambda *a,**kw:[]):
            with self.assertRaisesRegex(ValueError,'WEB patch incomplete'):self.finish(contexts)
        self.model.parts['COLUMN_FRONT'].stations.remove(1.55)
        with self.assertRaisesRegex(ValueError,'cylindrical'):self.finish(contexts)

    def test_complete_dp_runtime_six_ties_two_rps_four_couplings_and_repeat(self):
        groups=[]
        for i,rule in enumerate(self.rules,1):
            column=rule['column'];gid='HOOP_%02d'%i;lo=column['origin'][2]+.6;hi=lo+.08
            subset=copy.deepcopy(self.summary);components=copy.deepcopy(self.components)
            components.append(dict(component_code='HOOP',part_name='HOOP',section_kind='HOOP_BAND',model_policy='SOLID',
                                   thickness_m=.006,section_params_m=dict(width_m=.08,inner_radius_m=.0885)))
            for label,half in (('A',1),('B',-1)):
                name=gid+'_'+label
                subset['instances'].append(dict(component_code='HOOP',canonical_role='HOOP',instance_name=name,
                    part_name='HOOP',connection_group=gid,placement=dict(translation=[0,0,lo],rotation_steps=[])))
                h=NS(name=name,partName='HOOP',dependent='ON',vertices=[],faces=cc.Faces())
                for radius,flat,normal in ((.0885,False,-1),(.0945,False,1),(.0885,True,-1)):
                    ids=[]
                    for z in (lo,hi):
                        for x in (radius,-radius):
                            ids.append(len(h.vertices));h.vertices.append(NS(pointOn=((x,0,z),)))
                    h.faces.append(hh.CurvedFace(len(h.faces),radius,lo,hi,half,ids,instance=name,normal_sign=normal,flat=flat))
                self.a.instances[name]=h
            group=resolve_hoop(subset,components,column_role=column['role'])
            group['column']['partition_namespace']=gid
            for h in group['halves']:
                tail=column['role']+'_'+gid+'_'+h['label']
                h.update(column_region='STEP05_REGION_'+tail,hoop_region='STEP05_REGION_HOOP_'+tail,tie='STEP05_TIE_'+tail)
            groups.append(group)
        self.model.parts['HOOP']=NS(name='HOOP',features={},cells=[1],elements=[1])
        original_set=self.a.Set
        def set_after_all_partitions(name,**kw):
            for rule in self.rules:
                part=self.model.parts[rule['column']['part_name']]
                self.assertIn(1.55,part.stations)
                self.assertIsNotNone(part.split)
            return original_set(name,**kw)
        self.a.Set=set_after_all_partitions
        ties=[c['tie'] for c in self.plan['connections']]+[h['tie'] for g in groups for h in g['halves']]
        self.plan.update(column_hoop_groups=groups,warnings=['fixture diagnostic'],expected_constraints=dict(
            ties=ties,tie_count=6,rp_names=[r['rp_name'] for r in self.rules],reference_points=2,
            coupling_names=[t['coupling'] for r in self.rules for t in r['targets']],couplings=4))
        def run(fingerprint='dp-fixture'):
            with contextlib.redirect_stdout(io.StringIO()):
                self.rt['execute_dp'](self.plan,self.base.mdb,str(self.base.report),fingerprint,
                    'XYPLANE','ON','OFF','COMPUTED','DISTRIBUTING','WHOLE_SURFACE','UNIFORM')
        run()
        report=json.loads(self.base.report.read_text())
        self.assertEqual(report['actual_counts'],dict(ties=6,reference_points=2,couplings=4))
        self.assertEqual(report['warnings'],['fixture diagnostic'])
        self.assertEqual(report['overall_status'],'SUCCESS')
        self.assertEqual(len(self.model.constraints),10)
        self.assertEqual(len(report['column_hoop_groups']),2)
        self.assertEqual(len(report['column_beam_couplings']),2)
        self.assertIn('BEAM',report['mesh_removed'])
        self.assertEqual(self.model.parts['HOOP'].elements,[1])
        before={n:len(p.features) for n,p in self.model.parts.items()}
        run()
        self.assertEqual(before,{n:len(p.features) for n,p in self.model.parts.items()})
        self.assertEqual(len(self.a.referencePoints),2);self.assertEqual(len(self.model.constraints),10)
        with self.assertRaisesRegex(ValueError,'matching successful report'):run('different-plan')
