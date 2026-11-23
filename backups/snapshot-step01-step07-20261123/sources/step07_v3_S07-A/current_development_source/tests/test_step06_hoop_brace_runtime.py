import unittest
from types import SimpleNamespace as NS
from cadtocae.hoop_brace_setup import hoop_brace_source

class Face:
    def __init__(self,index,points,area):self.index=index;self.points=points;self.area=area;self.ids=[]
    def getVertices(self):return self.ids
    def getCentroid(self):return tuple(sum(p[i] for p in self.points)/len(self.points) for i in range(3))
    def getSize(self,**kw):return self.area
    def getNormal(self,**kw):return (1,0,0)
class Faces(list):
    def findAt(self,args,**kw):
        point=args[0]
        for face in self:
            if face.getCentroid()==point:return face
        raise ValueError('missing face')

class HoopBraceRuntimeTests(unittest.TestCase):
    def runtime(self):
        ns={'__name__':'test'};exec(hoop_brace_source({},'unused'),ns);return ns
    def model(self,partitioned=True):
        def web(i,a,b):return Face(i,[(0,0,a),(0,.07,a),(0,.07,b),(0,0,b)],.07*(b-a))
        faces=[web(0,0,.05 if partitioned else .2),web(1,.05,.15),web(2,.15,.2),
               Face(3,[(0,0,0),(.025,0,0),(.025,0,.05),(0,0,.05)],.025*.05)]
        vertices=[]
        for face in faces:
            for point in face.points:face.ids.append(len(vertices));vertices.append(NS(pointOn=(point,)))
        part=NS(cells=[],faces=Faces(faces),vertices=vertices)
        return NS(parts={'brace':part}),NS(partName='brace',faces=Faces(faces),vertices=vertices)
    def test_select_start_web_only_without_fixed_indices(self):
        ns=self.runtime();m,i=self.model();p={'translation':[0,0,0],'rotation_steps':[]}
        faces,r=ns['hb_web'](m,i,p)
        self.assertEqual([f.index for f in faces],[0])
        self.assertAlmostEqual(r['area'],.0035)
        self.assertEqual(r['station_m'],[0,.05])
    def test_unpartitioned_web_fails(self):
        ns=self.runtime();m,i=self.model(False)
        with self.assertRaisesRegex(ValueError,'BRACE_START_50MM_WEB_MISSING'):
            ns['hb_web'](m,i,{'translation':[0,0,0],'rotation_steps':[]})
    def test_self_contained_runtime_python2_no_part_mutation(self):
        from lib2to3.refactor import RefactoringTool
        source=hoop_brace_source({},'unused')
        RefactoringTool([]).refactor_string(source,'hoop_brace.py')
        for forbidden in ('CutExtrude(', 'PartitionFaceBy', 'deleteMesh(', 'ConnectorForce('):self.assertNotIn(forbidden,source)
    def test_names_do_not_collide_with_existing_bolts(self):
        ns=self.runtime()
        for side in ('FRONT','REAR'):
            new=set(ns['hb_names'](side).values())
            for group in ('P01','P02','P03','P04'):
                self.assertFalse(new.intersection(ns['b1_names'](group).values()))
                self.assertFalse(new.intersection(ns['sb_names'](group).values()))
