import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace as NS
from cadtocae.step07_bc_setup import generate_stage2
from cadtocae import step07_bc_runtime as rt
import math

# Runtime is normally appended to step07_runtime; pure geometry tests need math.
rt.math=math

class Stage2Tests(unittest.TestCase):
    def row(self):
        return dict(canonical_role='PURLIN_LOCAL',geometry_info=dict(length=.05),
                    placement=dict(translation=[2,.045,3],rotation_steps=[dict(axis_direction=[1,0,0],angle_deg=90)]))

    def instance(self):
        vertices=[NS(pointOn=[p]) for p in ([2,.045,3],[3,.045,3],[2,-.005,3],[3,-.005,3])]
        class Edge:
            def __init__(self,index,ids):
                self.index=index;self.ids=ids;self.pointOn=[vertices[ids[0]].pointOn[0]]
            def getVertices(self):return self.ids
            def getCurvature(self,parameter):raise ValueError('line')
        return NS(name='PURLIN_LOCAL_01',vertices=vertices,edges=[Edge(0,(0,1)),Edge(1,(2,3)),Edge(2,(0,2)),Edge(3,(1,3))],cells=[],faces=[])

    def test_local_front_rear_not_global_y_sign(self):
        i=self.instance();row=self.row()
        front=rt.b2_end(i,row,'FRONT',2e-6)['data'];rear=rt.b2_end(i,row,'REAR',2e-6)['data']
        self.assertEqual(front['diagnostic_indices'],[0]);self.assertEqual(rear['diagnostic_indices'],[1])
        self.assertEqual(front['bbox_m']['min'][1],.045)
        self.assertEqual(rear['bbox_m']['min'][1],-.005)

    def test_length_and_placement_mismatch_stop(self):
        row=self.row();row['geometry_info']['length']=.1
        with self.assertRaisesRegex(ValueError,'LENGTH'):rt.b2_end(self.instance(),row,'FRONT',2e-6)
        row=self.row();row['placement']['translation'][1]=.1
        with self.assertRaisesRegex(ValueError,'PLACEMENT'):rt.b2_end(self.instance(),row,'FRONT',2e-6)

    def test_shared_vertex_conflict(self):
        i=self.instance();target=rt.b2_end(i,self.row(),'FRONT',2e-6)
        i.edges[2].instanceName=i.name
        region=NS(edges=[i.edges[2]],faces=[])
        m=NS(rootAssembly=NS(surfaces={'hole':region},sets={}),constraints={'existing':NS(surface=('hole',),suppressed=False)},boundaryConditions={})
        with self.assertRaisesRegex(ValueError,'OVERLAP'):rt.b2_conflicts(m,target)

    def test_unresolved_constraint_fails_closed(self):
        target=rt.b2_end(self.instance(),self.row(),'FRONT',2e-6)
        m=NS(rootAssembly=NS(surfaces={},sets={}),constraints={'existing':NS(surface=('unknown',),suppressed=False)},boundaryConditions={})
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'):rt.b2_conflicts(m,target)

    def test_generator_versions_and_manual_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);src=p/'accepted.cae';src.write_bytes(b'accepted')
            summary=p/'summary.json';summary.write_text(json.dumps(dict(project_id='DP_FULL_ID',model_name='DP_FULL_ID',instances=[])))
            first=generate_stage2(summary,src,p);second=generate_stage2(summary,src,p)
            self.assertTrue(first['script'].endswith('DP_FULL_ID_step07_02_bc.py'))
            self.assertTrue(second['script'].endswith('_bc_v2.py'))
            self.assertEqual(Path(first['plan']['manual_working_copy']).read_bytes(),b'accepted')
            self.assertEqual(Path(first['plan']['output_cae']).parent,p/'CAE_Results')
            self.assertFalse(Path(first['plan']['output_cae']).exists())
            self.assertEqual(src.read_bytes(),b'accepted')

    def test_no_unapproved_group_or_mode(self):
        with self.assertRaises(ValueError):generate_stage2('unused','unused','unused',groups=('P02',))
        with self.assertRaises(ValueError):generate_stage2('unused','unused','unused',mode='ALL')

if __name__=='__main__':unittest.main()
