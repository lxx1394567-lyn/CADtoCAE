import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cadtocae.step07_batch import scan_projects,run_batch,digest

class BatchTests(unittest.TestCase):
    def make(self,root,project='SP_SC_ANG18_FULL001'):
        root.mkdir(parents=True,exist_ok=True)
        s=dict(project_id=project,model_name=project,structure_type='SP_SC',instances=[dict(instance_name='Base',part_name='B',canonical_role='COLUMN_DOWN'),dict(instance_name='P1',part_name='P',canonical_role='PURLIN_LOCAL',connection_group='P01')])
        for suffix,data in [('_assembly_summary.json',s),('_analysis_plan.json',dict(project_id=project)),('_static_loads.json',dict(schema_version=1,project_id=project,units='m-N-Pa',coordinate_system='GLOBAL',loads=[dict(instance='P1',force=[10,20,-30])]))]:
            (root/(project+suffix)).write_text(json.dumps(data))
        (root/(project+'_final.cae')).write_bytes(b'cae');return project
    def test_stage1_without_load_or_connection(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            for suffix in ('_static_loads.json','_analysis_plan.json'):(p/(name+suffix)).unlink()
            row=scan_projects(p)['projects'][0]
            self.assertTrue(row['ready']);self.assertEqual(set(row['files']),{'summary','cae'})
            self.assertNotIn('loads',row['config']);self.assertEqual(row['config']['stage'],1)
            with self.assertRaises(ValueError):scan_projects(p,stage=2)
    def test_no_cross_folder_pairing(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p/'a');self.make(p/'b');(p/'a'/(name+'_assembly_summary.json')).unlink()
            rows=scan_projects(p)['projects'];self.assertEqual([r['ready'] for r in rows],[True])
    def test_skip_outputs_backups(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);self.make(p/'Step07_Results');self.make(p/'backups');self.make(p/'other');(p/'other'/'step07_plan.json').write_text('{}')
            self.assertEqual(len(scan_projects(p)['projects']),1)
    def test_duplicate_plain_cae_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);(p/'CAE_Results').mkdir();(p/'CAE_Results'/(name+'_final.cae')).write_bytes(b'other')
            self.assertFalse(scan_projects(p)['projects'][0]['ready'])
    def test_manifest_stage_and_hash(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            for stage in (5,6):
                cae=p/(name+'_final_'+str(stage)*16+'.cae');cae.write_bytes(str(stage).encode());cae.with_suffix('.delivery.json').write_text(json.dumps(dict(status='PASSED',save_status='SAVED',model=name,upstream_stage="Step0"+str(stage),sha256=digest(cae))))
            r=scan_projects(p)['projects'][0];self.assertTrue(r['ready']);self.assertTrue(r['files']['cae'].endswith('6'*16+'.cae'))
            cae.write_bytes(b'changed');self.assertFalse(scan_projects(p)['projects'][0]['ready'])
    def test_invalid_load_does_not_block_stage1(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);(p/(name+'_static_loads.json')).write_text('invalid JSON')
            self.assertTrue(scan_projects(p)['projects'][0]['ready'])
    def test_timestamp_delivery_and_backup_name(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            for suffix in ('20261011-090732_09186016','backup'):
                f=p/(name+'_final_'+suffix+'.cae');f.write_bytes(b'version')
                f.with_suffix('.delivery.json').write_text(json.dumps(dict(status='PASSED',save_status='SAVED',model=name,stage=5,sha256=digest(f))))
            r=scan_projects(p)['projects'][0]
            self.assertTrue(r['ready']);self.assertIn('20261011-090732_09186016',r['files']['cae'])
    def test_failure_continues_and_cancel_skips(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            for n in ('A','B','C'):self.make(p,n)
            s=scan_projects(p);selected={r['key'] for r in s['projects'][:2]}
            with patch('cadtocae.step07_batch.new_run',return_value=p),patch('cadtocae.step07_batch.execute',side_effect=[ValueError('bad mesh'),dict(status='SETUP_COMPLETE')]):
                r=run_batch(s,selected,'unused',mode='automatic')
            self.assertEqual([x['status'] for x in r['projects']],['FAILED','SUCCESS','SKIPPED'])
    def test_changed_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);s=scan_projects(p);(p/(name+'_final.cae')).write_bytes(b'new')
            with patch('cadtocae.step07_batch.execute') as e:r=run_batch(s,{s['projects'][0]['key']},'unused');e.assert_not_called()
            self.assertEqual(r['counts']['FAILED'],1)
    def test_default_generates_standalone_py_without_abaqus(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);project=self.make(p);s=scan_projects(p)
            with patch('cadtocae.step07_batch.execute') as execute:
                r=run_batch(s,{s['projects'][0]['key']})
                execute.assert_not_called()
            row=r['projects'][0];self.assertEqual(row['status'],'GENERATED')
            script=Path(row['script']);self.assertEqual(script.name,project+'_step07_01_step.py')
            code=script.read_text(encoding='utf-8')
            self.assertIn('s7_run_stage1_logged(STAGE1_PLAN)',code)
            self.assertNotIn('from cadtocae',code)
            self.assertFalse(list((script.parent/'CAE_Results').glob('*.cae')))
            self.assertEqual(script.parent,p)
            self.assertFalse((p/'Step07_Results').exists())
            self.assertFalse((script.parent/'step07_submit_job.py').exists())
    def test_step04_without_delivery(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            (p/(name+'_final.cae')).rename(p/(name+'_step04.cae'))
            r=scan_projects(p)['projects'][0]
            self.assertTrue(r['ready']);self.assertEqual(r['upstream']['stage'],'Step04')
            self.assertFalse(r['upstream']['engineering_verified'])
    def test_summary_recognized_without_cae(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);(p/(name+'_final.cae')).unlink()
            r=scan_projects(p)['projects'][0]
            self.assertTrue(r['checks']['project_identified']);self.assertFalse(r['ready'])
    def test_internal_id_and_arbitrary_cae_metadata(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            (p/(name+'_assembly_summary.json')).rename(p/'renamed_assembly_summary.json')
            f=p/'checkpoint.cae';(p/(name+'_final.cae')).rename(f)
            f.with_suffix('.source.json').write_text(json.dumps(dict(project_id=name,upstream_stage='Step04',sha256=digest(f))))
            r=scan_projects(p)['projects'][0]
            self.assertEqual(r['project_id'],name);self.assertTrue(r['ready'])
    def test_same_stage_different_dates_ambiguous(self):
        import os
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p)
            for n in (1,2):
                f=p/(name+'_v'+str(n)+'.cae');f.write_bytes(str(n).encode())
                m=f.with_suffix('.source.json');m.write_text(json.dumps(dict(project_id=name,upstream_stage='Step04')))
                os.utime(m,(n*100000,n*100000))
            self.assertFalse(scan_projects(p)['projects'][0]['ready'])
    def test_unknown_versions_do_not_rank_by_filename(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);(p/(name+'_step06.cae')).write_bytes(b'other')
            self.assertFalse(scan_projects(p)['projects'][0]['ready'])
    def test_full_identifier_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);(p/(name+'_final.cae')).unlink()
            (p/(name+'2_step04.cae')).write_bytes(b'other')
            self.assertFalse(scan_projects(p)['projects'][0]['ready'])
    def test_batchrunner_stage2_is_step04(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);name=self.make(p);f=p/(name+'_final.cae')
            f.with_suffix('.delivery.json').write_text(json.dumps(dict(status='PASSED',save_status='SAVED',model=name,stage=2,sha256=digest(f))))
            r=scan_projects(p)['projects'][0];self.assertEqual(r['upstream']['stage'],'Step04')
    def test_flat_reuse_and_version_protection(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p);keys={scan['projects'][0]['key']}
            first=run_batch(scan,keys)['projects'][0];script=Path(first['script']);original=script.read_bytes()
            same=run_batch(scan,keys)['projects'][0];self.assertEqual(first['script'],same['script'])
            plan=first['plan'];self.assertEqual(Path(plan['output_dir']),p)
            self.assertEqual(Path(plan['output_cae']).parent,p/'CAE_Results')
            Path(plan['output_cae']).write_bytes(b'accepted cae')
            Path(plan['report_path']).write_bytes(b'accepted report')
            newer=run_batch(scan,keys)['projects'][0]
            self.assertTrue(newer['script'].endswith('_step_v2.py'))
            self.assertTrue(newer['plan']['output_cae'].endswith('_step07_01_v2.cae'))
            self.assertEqual(script.read_bytes(),original)
            self.assertEqual(Path(plan['report_path']).read_bytes(),b'accepted report')
            self.assertEqual(Path(plan['output_cae']).read_bytes(),b'accepted cae')
    def test_changed_script_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p);keys={scan['projects'][0]['key']}
            row=run_batch(scan,keys)['projects'][0];Path(row['script']).write_bytes(b'user edits')
            new=run_batch(scan,keys)['projects'][0]
            self.assertTrue(new['script'].endswith('_v2.py'));self.assertEqual(Path(row['script']).read_bytes(),b'user edits')
    def test_multi_project_flat_names_are_disjoint(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p,'DP_ANG14_FULL001');self.make(p,'DP_ANG14_FULL002')
            scan=scan_projects(p);rows=run_batch(scan,{r['key'] for r in scan['projects']})['projects']
            for key in ('output_cae','report_path','log_path','scratch_cae','plan_path'):
                self.assertEqual(len({r['plan'][key] for r in rows}),2)
            self.assertEqual(len(scan_projects(p)['projects']),2)
    def test_automatic_receives_exact_project_plan(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p)
            with patch('cadtocae.step07_batch.execute',return_value={'status':'SETUP_COMPLETE'}) as execute:
                row=run_batch(scan,{scan['projects'][0]['key']},'unused',mode='automatic')['projects'][0]
            self.assertEqual(execute.call_args.kwargs['stage_plan'],row['plan'])
            self.assertEqual(row['status'],'SUCCESS')
    def test_modes_are_explicit_and_use_distinct_versions(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p);keys={scan['projects'][0]['key']}
            manual=run_batch(scan,keys)['projects'][0]
            self.assertEqual(manual['plan']['execution_mode'],'CURRENT_SESSION_DEBUG')
            with patch('cadtocae.step07_batch.execute',return_value={'status':'SETUP_COMPLETE'}):
                automatic=run_batch(scan,keys,mode='automatic')['projects'][0]
            self.assertEqual(automatic['plan']['execution_mode'],'INDEPENDENT_CAE')
            self.assertNotEqual(manual['script'],automatic['script'])
            self.assertIn('s7_apply_static_step(db,c,report)',Path(manual['script']).read_text(encoding='utf-8'))
    def test_session_backup_reserves_version(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p);keys={scan['projects'][0]['key']}
            row=run_batch(scan,keys)['projects'][0]
            Path(row['plan']['session_backup_cae']).write_bytes(b'recovery')
            new=run_batch(scan,keys)['projects'][0]
            self.assertEqual(new['plan']['output_version'],2)
            self.assertEqual(Path(row['plan']['session_backup_cae']).read_bytes(),b'recovery')
    def test_two_stage_parameters_and_chain(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.make(p);scan=scan_projects(p)
            row=run_batch(scan,{scan['projects'][0]['key']})['projects'][0]
            steps=row['plan']['steps']
            self.assertEqual([s['name'] for s in steps],['STEP07_PRELOAD','STEP07_LOADING'])
            self.assertEqual([s['previous'] for s in steps],['Initial','STEP07_PRELOAD'])
            for s in steps:
                self.assertEqual((s['nlgeom'],s['timePeriod'],s['timeIncrementationMethod'],s['initialInc'],s['minInc'],s['maxInc'],s['maxNumInc']),
                                 (False,1.0,'AUTOMATIC',0.01,1e-7,1.0,1000000))
if __name__=='__main__':unittest.main()
