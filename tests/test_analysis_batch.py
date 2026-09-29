"""Folder safety, independent publication, and family discovery fixtures."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_analysis_beam_brace_tie as bb
from cadtocae.analysis_discovery import scan_projects, identity, ROLES
from cadtocae.analysis_batch import generate_batch
from cadtocae.runtime_compatibility import assert_runtime_compatible
from cadtocae.analysis_defaults import default_analysis_config, DEFAULT_SP_SC_ANALYSIS_CONFIG


def snapshot(root):
    return {str(p.relative_to(root)):identity(p) if p.is_file() else 'directory' for p in root.rglob('*')}


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture=bb.PlannerTests();self.addCleanup(self.fixture.doCleanups);self.fixture.setUp()
        self.root=self.fixture.root
        self.source=self.root/'source';self.source.mkdir()
        self.output=self.root/'output'
        for p in list(self.root.iterdir()):
            if p.is_file():shutil.move(str(p),self.source/p.name)
        self.project=self.fixture.summary['project_id']
        self.summary=self.source/(self.project+'_assembly_summary.json')
        self.data=json.loads(self.summary.read_text())
        for role in ('COLUMN_UP','COLUMN_DOWN'):
            self.data['instances'].append(dict(component_code=role,canonical_role=role,part_name='P_'+role,instance_name=role+'_01'))
        for label in ('A','B'):
            self.data['instances'].append(dict(component_code='HOOP',canonical_role='HOOP',part_name='P_HOOP',instance_name='HOOP_01_'+label,connection_group='HOOP_01'))
        self.data['assembly_points']['F']=[0,0,1]
        self.write()
        self.rows=[dict(component_code=role,abaqus_part_name='P_'+role,section_kind='HOOP_BAND' if role=='HOOP' else 'C_CHANNEL') for role in (*ROLES,'HOOP')]
        self.enterContext(patch('cadtocae.analysis_discovery.load_dimension_complete_components',side_effect=lambda _:self.rows))
        self.enterContext(patch('cadtocae.analysis_discovery.component_code_from_row',side_effect=lambda r:r['component_code']))
        from cadtocae.main_frame_assembly import _read_named_points
        self.read_points=_read_named_points
        def points(path):
            p,s=self.read_points(path);p['F']=[0,0,1];return p,s
        self.enterContext(patch('cadtocae.analysis_discovery._read_named_points',side_effect=points))

    def write(self):self.summary.write_text(json.dumps(self.data),encoding='utf-8')

    def scan(self):return scan_projects(self.source)

    def test_scan_is_pure_read_only_and_ready(self):
        before=snapshot(self.source)
        with patch('tempfile.TemporaryDirectory',side_effect=AssertionError('Scan must not write scratch')):
            result=self.scan()
        self.assertEqual(snapshot(self.source),before);self.assertFalse(self.output.exists())
        r=result['projects'][0]
        self.assertEqual(r['status'],'READY');self.assertEqual(len(r['supported_rules']),4)

    def test_optional_py_absent_and_never_parsed(self):
        for p in self.source.glob('*.py'):p.unlink()
        r=self.scan()['projects'][0]
        self.assertEqual(r['status'],'READY');self.assertEqual(len(r['warnings']),2)

    def test_missing_each_required_input(self):
        for suffix in ('components.xlsx','coordinate.xlsx','assembly_summary.json'):
            p=self.source/(self.project+'_'+suffix);data=p.read_bytes();p.unlink()
            try:self.assertEqual(self.scan()['projects'][0]['status'],'INPUT_INCOMPLETE')
            finally:p.write_bytes(data)

    def test_unsupported_and_invalid_summary(self):
        for structure in ('UNKNOWN','DP'):
            self.data['structure_type']=structure;self.write()
            self.assertEqual(self.scan()['projects'][0]['status'],'UNSUPPORTED_STRUCTURE')
        self.summary.write_text('{')
        self.assertEqual(self.scan()['projects'][0]['status'],'NEEDS_REVIEW')

    def test_missing_role_and_component(self):
        self.data['instances']=[m for m in self.data['instances'] if m['component_code']!='COLUMN_UP'];self.write()
        r=self.scan()['projects'][0]
        self.assertIn('COLUMN_UP',r['missing_requirements']['roles'])
        self.assertEqual(r['status'],'NEEDS_REVIEW')

    def test_missing_point(self):
        del self.data['assembly_points']['E'];self.write()
        self.assertIn('E',self.scan()['projects'][0]['missing_requirements']['points'])

    def test_missing_hoop_pair(self):
        self.data['instances'].pop();self.write()
        self.assertTrue(self.scan()['projects'][0]['missing_requirements']['hoop_groups'])

    def test_hoop_assembly_and_angle_variants(self):
        for angle in (18,28,33):
            project='FAMILY_ANGLE_'+str(angle)
            folder=self.root/str(angle);shutil.copytree(self.source,folder)
            for p in list(folder.iterdir()):
                if p.name.startswith(self.project):p.rename(folder/p.name.replace(self.project,project))
            summary=folder/(project+'_assembly_summary.json')
            s=copy.deepcopy(self.data);s.update(project_id=project,model_name=project)
            for m in s['instances']:
                if m['component_code']=='HOOP':m['component_code']='HOOP_ASSEMBLY_1'
            summary.write_text(json.dumps(s))
            self.rows[-1]['component_code']='HOOP_ASSEMBLY_1'
            self.assertEqual(scan_projects(folder)['projects'][0]['status'],'READY')

    def test_default_nonrecursive_duplicate_detection(self):
        child=self.source/'copy';shutil.copytree(self.source,child)
        self.assertEqual(len(self.scan()['projects']),1)
        rows=scan_projects(self.source,True)['projects']
        self.assertEqual(len(rows),2);self.assertTrue(all(r['status']=='NEEDS_REVIEW' for r in rows))

    def test_no_cross_directory_merge(self):
        child=self.source/'child';child.mkdir()
        self.summary.rename(child/self.summary.name)
        rows=scan_projects(self.source,True)['projects']
        self.assertFalse(any(r['status']=='READY' for r in rows))
        for r in rows:self.assertTrue(r['missing_requirements']['files'])

    def beam_only(self):
        self.enterContext(patch('cadtocae.beam_brace_tie.build_column_plan',return_value=None))
        self.enterContext(patch('cadtocae.beam_brace_tie.build_hoop_plan',return_value=None))
        self.enterContext(patch('cadtocae.beam_brace_tie.build_coupling_plan',return_value=None))

    def test_incomplete_cannot_generate(self):
        self.summary.unlink()
        with self.assertRaisesRegex(ValueError,'No READY'):generate_batch(self.scan())
        self.assertFalse(list(self.source.glob('*_analysis_setup.py')))

    def test_same_folder_generation_and_input_preservation(self):
        self.beam_only();before=snapshot(self.source)
        result=generate_batch(self.scan());row=result['projects'][0]
        self.assertEqual(row['generation_status'],'GENERATED',row['errors'])
        self.assertEqual(row['input_status'],'READY')
        for name,value in before.items():self.assertEqual(snapshot(self.source)[name],value)
        self.assertTrue(all(Path(p).parent==self.source for p in row['generated_files'].values()))
        self.assertFalse(any(p.is_dir() for p in self.source.iterdir()))
        source=Path(row['generated_files']['script']).read_text(encoding='utf-8')
        assert_runtime_compatible(source);self.assertNotIn('.step05-tmp-',source)
        self.assertTrue((self.source/'step05_batch_summary.json').exists())
        summary=json.loads((self.source/'step05_batch_summary.json').read_text())
        self.assertEqual(summary['generation_counts'],{'succeeded':1,'failed':0})

    def test_internal_config_and_generated_files_rebuilt(self):
        self.beam_only()
        first=generate_batch(self.scan());row=first['projects'][0]
        self.assertFalse((self.source/(self.project+'_analysis.xlsx')).exists())
        plan=json.loads(Path(row['generated_files']['plan']).read_text())
        self.assertEqual(plan['analysis_config'],DEFAULT_SP_SC_ANALYSIS_CONFIG)
        self.assertEqual(plan['source_files']['analysis_config'],'DEFAULT_SP_SC_ANALYSIS_CONFIG')
        self.assertNotIn('analysis',plan['source_files'])
        for key in ('plan','script'):Path(row['generated_files'][key]).write_text('stale')
        second=generate_batch(first)['projects'][0]
        self.assertEqual(second['generation_status'],'GENERATED')
        for key in ('plan','script'):self.assertNotEqual(Path(row['generated_files'][key]).read_text(),'stale')


    def test_existing_complete_and_partial_outputs(self):
        self.assertEqual(self.scan()['projects'][0]['generation_status'],'NOT_GENERATED')
        (self.source/(self.project+'_analysis.xlsx')).write_text('ignored old config')
        self.assertEqual(self.scan()['projects'][0]['generation_status'],'NOT_GENERATED')
        plan=self.source/(self.project+'_analysis_plan.json');plan.write_text('{}')
        self.assertEqual(self.scan()['projects'][0]['generation_status'],'PARTIAL')
        plan.unlink();(self.source/(self.project+'_analysis_setup.py')).write_text('# existing')
        self.assertEqual(self.scan()['projects'][0]['generation_status'],'PARTIAL')
        self.beam_only();generate_batch(self.scan())
        row=self.scan()['projects'][0]
        self.assertEqual(row['generation_status'],'GENERATED');self.assertEqual(row['input_status'],'READY')


    def test_old_config_ignored_and_preserved(self):
        self.beam_only()
        config=self.source/(self.project+'_analysis.xlsx');config.write_bytes(b'user invalid workbook')
        before=identity(config)
        row=generate_batch(self.scan())['projects'][0]
        self.assertEqual(row['generation_status'],'GENERATED');self.assertEqual(identity(config),before)


    def test_changed_input_since_scan_rejected(self):
        scan=self.scan();self.summary.write_text(self.summary.read_text()+' ')
        row=generate_batch(scan)['projects'][0]
        self.assertEqual(row['generation_status'],'FAILED')
        self.assertFalse((self.source/(self.project+'_analysis.xlsx')).exists())

    def test_selected_only(self):
        scan=self.scan()
        with self.assertRaisesRegex(ValueError,'No READY'):generate_batch(scan,set())
        self.beam_only()
        r=generate_batch(scan,{(str(self.source),self.project)})
        self.assertEqual(r['generation_counts']['succeeded'],1)

    def test_one_failure_continues_and_progress(self):
        child=self.source/'child';shutil.copytree(self.source,child)
        for p in list(child.iterdir()):
            if p.name.startswith(self.project):p.rename(child/p.name.replace(self.project,'SECOND'))
        data=copy.deepcopy(self.data);data.update(project_id='SECOND',model_name='SECOND')
        (child/'SECOND_assembly_summary.json').write_text(json.dumps(data))
        scan=scan_projects(self.source,True);events=[]
        def stub(files,analysis,stage,final_output_dir):
            name=files.assembly_summary.name.removesuffix('_assembly_summary.json')
            if name==self.project:raise RuntimeError('synthetic failure')
            for suffix in ('_analysis_plan.json','_analysis_setup.py'):(stage/(name+suffix)).write_text('test')
        with patch('cadtocae.analysis_batch.generate',side_effect=stub):r=generate_batch(scan,progress=events.append)
        states={row['project_id']:row['generation_status'] for row in r['projects']}
        self.assertEqual(states,{self.project:'FAILED','SECOND':'GENERATED'})
        self.assertEqual(r['generation_counts'],{'succeeded':1,'failed':1})
        self.assertEqual(len(events),4)
        self.assertTrue((self.source/'SECOND_analysis_setup.py').exists())
        self.assertFalse((child/'SECOND_analysis_setup.py').exists())

    def test_partial_generator_result_not_published(self):
        with patch('cadtocae.analysis_batch.generate',return_value={}):r=generate_batch(self.scan())
        self.assertEqual(r['projects'][0]['generation_status'],'FAILED')
        self.assertFalse((self.source/(self.project+'_analysis.xlsx')).exists())

    def test_publication_failure_rolls_back(self):
        self.beam_only();r=generate_batch(self.scan())
        paths={k:Path(v) for k,v in r['projects'][0]['generated_files'].items()}
        for key in ('plan','script'):paths[key].write_text('old '+key)
        before={k:identity(p) for k,p in paths.items()}
        import os
        replace=os.replace
        def fail_script(src,dst):
            if Path(src).parent.name.startswith('.step05-tmp-') and Path(dst)==paths['script']:raise OSError('publish failure')
            return replace(src,dst)
        with patch('cadtocae.analysis_batch.os.replace',side_effect=fail_script):r=generate_batch(self.scan())
        self.assertEqual(r['projects'][0]['generation_status'],'FAILED')
        self.assertEqual({k:identity(p) for k,p in paths.items()},before)

    def test_frozen_rules_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        baseline=root/'outputs/step05_batch_dev/frozen_hashes.json'
        if not baseline.exists():self.skipTest('Local development baseline unavailable')
        for name,digest in json.loads(baseline.read_text()).items():
            if name in ('column_column_tie.py','column_hoop_tie.py','column_beam_coupling.py','column_hoop_tie_runtime.py','tie_preflight_runtime.py'):continue  # adapters / additive multi-group reporting; covered by behavior regressions
            self.assertEqual(identity(root/'src/cadtocae'/name)['sha256'],digest,name)

    def test_ang18_28_33_all_attempted_without_analysis_xlsx(self):
        for p in list(self.source.glob('*.xlsx')):
            if p.name=='analysis.xlsx':p.unlink()
        base=copy.deepcopy(self.data)
        for angle in (28,33):
            name='SP_SC_ANG%d_FIXTURE' % angle
            for p in list(self.source.iterdir()):
                if p.is_file() and p.name.startswith(self.project):shutil.copy2(p,self.source/p.name.replace(self.project,name))
            data=copy.deepcopy(base);data.update(project_id=name,model_name=name)
            (self.source/(name+'_assembly_summary.json')).write_text(json.dumps(data))
        seen=[];events=[]
        def stub(files,config,stage,final_output_dir):
            self.assertEqual(config,default_analysis_config())
            project=files.assembly_summary.name.removesuffix('_assembly_summary.json');seen.append(project)
            for suffix in ('_analysis_plan.json','_analysis_setup.py'):(stage/(project+suffix)).write_text('fixture')
        with patch('cadtocae.analysis_batch.generate',side_effect=stub):r=generate_batch(self.scan(),progress=events.append)
        self.assertEqual(len(seen),3);self.assertEqual(r['generation_counts'],{'succeeded':3,'failed':0})
        self.assertFalse(list(self.source.glob('*analysis.xlsx')))
        self.assertEqual([e['row']['generation_status'] for e in events],['GENERATING','GENERATED']*3)
