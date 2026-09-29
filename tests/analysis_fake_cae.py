"""Small independent planar-shell CAE test double, NOT an Abaqus substitute.

Clips polygons to simulate partitions and rebuilds topology. Used to test mutation
ordering, area preservation, complete region selection, and repeat execution.
"""
import math
from types import SimpleNamespace as NS


def sub(a, b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def length(v):
    return math.sqrt(dot(v,v))


def normalized(v):
    return tuple(x/length(v) for x in v)


class Repository(dict):
    def changeKey(self, fromName, toName):
        if toName in self:
            raise ValueError('name collision')
        self[toName]=self.pop(fromName)
        self[toName].name=toName


class Edge:
    def __init__(self, part, index, ids):
        self.part,self.index,self.ids=part,index,ids
        self.pointOn=(tuple(sum(part.vertices[j].pointOn[0][i] for j in ids)/2 for i in range(3)),)

    def getVertices(self):
        return self.ids

    def getSize(self, printResults=False):
        return length(sub(self.part.vertices[self.ids[0]].pointOn[0], self.part.vertices[self.ids[1]].pointOn[0]))


class Face:
    def __init__(self, part, index, ids):
        self.part,self.index,self.ids=part,index,ids

    def getVertices(self):
        return self.ids

    def getNormal(self):
        p=[self.part.vertices[i].pointOn[0] for i in self.ids]
        return normalized(cross(sub(p[1],p[0]), sub(p[2],p[0])))

    def getSize(self, printResults=False):
        p=[self.part.vertices[i].pointOn[0] for i in self.ids]
        return sum(length(cross(sub(p[i],p[0]), sub(p[i+1],p[0])))/2 for i in range(1,len(p)-1))


class DynamicStation:
    def __init__(self, part, station):
        self.part,self.station=part,station
        self.faces=[]

    @property
    def edges(self):
        return [e for e in self.part.edges if all(abs(self.part.vertices[i].pointOn[0][2]-self.station)<1e-8 for i in e.ids)]


class AllFaces:
    def __init__(self, part):
        self.part=part

    @property
    def faces(self):
        return self.part.faces


class Part:
    def __init__(self, name, width, height, lip, depth, stations=()):
        self.name=name
        profile=[(width,lip),(width,0),(0,0),(0,height),(width,height),(width,height-lip)]
        levels=[0.]+list(stations)+[depth]
        self.polygons=[]
        for a,b in zip(profile[:-1],profile[1:]):
            for low,high in zip(levels[:-1],levels[1:]):
                self.polygons.append([(a[0],a[1],low),(b[0],b[1],low),(b[0],b[1],high),(a[0],a[1],high)])
        self.sets={}
        self.surfaces={}
        self.features=Repository()
        self.datums={}
        self.cells=[]
        self.elements=[object()]
        self.mutations=[]
        self.sectionAssignments=[NS(suppressed=False,region=AllFaces(self),sectionName='shell',
                                    thicknessAssignment='FROM_SECTION',offsetType='MIDDLE_SURFACE',offset=0.)]
        self.rebuild()
        if stations:
            self.sets['SET_BEAM_SEC_C']=DynamicStation(self,stations[0])

    def rebuild(self):
        self.vertices=[]
        self.faces=[]
        self.edges=[]
        keys={}
        edgekeys=set()
        for poly in self.polygons:
            ids=[]
            for point in poly:
                key=tuple(round(x,10) for x in point)
                if key not in keys:
                    keys[key]=len(self.vertices)
                    self.vertices.append(NS(pointOn=(point,)))
                ids.append(keys[key])
            self.faces.append(Face(self,len(self.faces),tuple(ids)))
            for a,b in zip(ids,ids[1:]+ids[:1]):
                key=tuple(sorted((a,b)))
                if key not in edgekeys:
                    edgekeys.add(key)
                    self.edges.append(Edge(self,len(self.edges),key))

    def feature(self, prefix, datum=None):
        index=len(self.features)+1
        value=NS(id=index,name=prefix+str(index))
        self.features[value.name]=value
        if datum is not None:
            self.datums[index]=datum
        self.mutations.append(prefix)
        return value

    def DatumPointByCoordinate(self, coords):
        return self.feature('DatumPoint',NS(point=coords))

    def DatumPlaneByThreePoints(self, point1, point2, point3):
        return self.feature('DatumPlane',NS(point=point1.point, normal=normalized(cross(sub(point2.point,point1.point), sub(point3.point,point1.point)))))

    def PartitionFaceByDatumPlane(self, datumPlane, faces):
        p,n=datumPlane.point,datumPlane.normal
        result=[]
        for poly in self.polygons:
            distances=[dot(sub(x,p),n) for x in poly]
            if min(distances)>=-1e-8 or max(distances)<=1e-8:
                result.append(poly)
                continue
            for sign in (1,-1):
                clipped=[]
                for a,b in zip(poly,poly[1:]+poly[:1]):
                    da,db=dot(sub(a,p),n)*sign,dot(sub(b,p),n)*sign
                    if da>=-1e-8:
                        clipped.append(a)
                    if da*db<0:
                        clipped.append(tuple(a[i]+(b[i]-a[i])*da/(da-db) for i in range(3)))
                result.append(clipped)
        self.polygons=result
        self.rebuild()
        return self.feature('Partition')

    def deleteMesh(self):
        self.mutations.append('deleteMesh')
        self.elements=[]

    def Set(self, name, **kwargs):
        self.sets[name]=NS(faces=kwargs.get('faces',[]),edges=kwargs.get('edges',[]))
        self.mutations.append('Set')

    def Surface(self,name,**kwargs):
        key=next(iter(kwargs))
        self.surfaces[name]=NS(faces=kwargs[key],sides=('SIDE1' if key=='side1Faces' else 'SIDE2',))
        self.mutations.append('Surface')


class Instance:
    def __init__(self, name, part, rotation, translation):
        self.name,self.partName,self.dependent=name,part.name,'ON'
        self.part,self.rotation,self.translation=part,rotation,translation

    def mapped(self, p, translate=True):
        return tuple(dot(row,p)+(self.translation[i] if translate else 0) for i,row in enumerate(self.rotation))

    @property
    def vertices(self):
        return [NS(pointOn=(self.mapped(v.pointOn[0]),)) for v in self.part.vertices]

    @property
    def faces(self):
        return [NS(getVertices=f.getVertices,getNormal=lambda f=f:self.mapped(f.getNormal(),False)) for f in self.part.faces]

    @property
    def edges(self):
        return self.part.edges


def fake_model_and_summary():
    # Synthetic dimensions, not engineering benchmark data.
    beam=Part('P_INCLINED_BEAM',.1,.2,.025,2.,(1.,))
    brace=Part('P_BRACE_FRONT',.05,.04,.01,1.)
    s=math.sqrt(.5)
    rotation_beam=((0.,0.,1.),(1.,0.,0.),(0.,1.,0.))
    rotation_brace=((0.,-s,s),(1.,0.,0.),(0.,s,s))
    translation_brace=(1.-s,.025,.020-s)
    instances={}
    summary={'project_id':'SYNTHETIC_A2','model_name':'SYNTHETIC_A2','assembly_points':{'C':[1.,0.,.1]},
             'assembly_info':{'executor_version':'step04-instance-plan-v1'},'instances':[]}
    for role,part,rotation,translation,angle in [('INCLINED_BEAM',beam,rotation_beam,(0.,0.,0.),90.),
                                               ('BRACE_FRONT',brace,rotation_brace,translation_brace,45.)]:
        name=role+'_01'
        instances[name]=Instance(name,part,rotation,translation)
        summary['instances'].append({'instance_name':name,'part_name':part.name,'component_code':role,'canonical_role':role,
                                     'geometry_info':{'length':2. if part is beam else 1.,'section_kind':'C_CHANNEL'},
                                     'placement':{'translation':translation,'rotation_steps':[
                                         {'axis_point':[0,0,0],'axis_direction':[0,0,1],'angle_deg':90.},
                                         {'axis_point':[0,0,0],'axis_direction':[0,1,0],'angle_deg':angle}]}})
    assembly=NS(instances=instances,regenerate=lambda:None)
    model=NS(parts={p.name:p for p in (beam,brace)},rootAssembly=assembly,
             sections={'shell':NS(thickness=.004,thicknessType='UNIFORM')})
    return NS(models={'SYNTHETIC_A2':model}),summary
