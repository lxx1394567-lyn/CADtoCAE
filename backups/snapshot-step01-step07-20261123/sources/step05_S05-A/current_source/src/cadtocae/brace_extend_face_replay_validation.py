# -*- coding: utf-8 -*-
# Exact geometry replay of the user-recorded Abaqus/CAE 2020 Macro1.
# Benchmark only: run on the same pre-operation topology as the recording.
from abaqus import mdb
import assembly
import mesh

a1 = mdb.models['SP_SC_ANG28_1042110101170S-T0204'].rootAssembly
a1.makeIndependent(instances=(a1.instances['BRACE_FRONT_01'], ))

a = mdb.models['SP_SC_ANG28_1042110101170S-T0204'].rootAssembly
f1 = a.instances['BRACE_FRONT_01'].faces
pickedRegions = f1.getSequenceFromMask(mask=('[#e ]', ), )
a.deleteMesh(regions=pickedRegions)

a = mdb.models['SP_SC_ANG28_1042110101170S-T0204'].rootAssembly
brace = a.instances['BRACE_FRONT_01']
faces_before = len(brace.faces)
edges_before = len(brace.edges)
print('faces_before = %d' % faces_before)
print('edges_before = %d' % edges_before)

f1 = a.instances['BRACE_FRONT_01'].faces
pickedFaces = f1.getSequenceFromMask(mask=('[#4 ]', ), )
f1 = a.instances['INCLINED_BEAM_01'].faces
a.PartitionFaceByExtendFace(extendFace=f1[18], faces=pickedFaces)
a.regenerate()

brace = a.instances['BRACE_FRONT_01']
faces_after = len(brace.faces)
edges_after = len(brace.edges)
print('faces_after = %d' % faces_after)
print('edges_after = %d' % edges_after)
print('remesh_required = True')
print('Material removed = False')
if faces_after <= faces_before or edges_after <= edges_before:
    raise ValueError('Extend-face partition did not modify BRACE_FRONT geometry')
