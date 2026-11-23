"""Python 2.7 runtime: read existing geometry; create only P01 connector objects."""
import json
import math

B1_NAMES = dict(rp_support='STEP06_RP_P01_SUPPORT',rp_purlin='STEP06_RP_P01_PURLIN',
    support_region='STEP06_REGION_P01_SUPPORT_HOLE',purlin_region='STEP06_REGION_P01_PURLIN_HOLE',
    support_surface='STEP06_SURF_P01_SUPPORT_HOLE',purlin_surface='STEP06_EDGE_P01_PURLIN_HOLE',
    support_coupling='STEP06_COUPLING_P01_SUPPORT',purlin_coupling='STEP06_COUPLING_P01_PURLIN',
    wire='STEP06_WIRE_P01_PURLIN_BOLT',connector_section='STEP06_CONNECTOR_SECTION_PURLIN_BOLT',
    orientation='STEP06_CSYS_P01_PURLIN_BOLT')


def b1_names(group):
    names = {}
    for key,value in B1_NAMES.items():
        names[key] = value.replace('P01',str(group))
    return names


def b1_frame(plan):
    a = tuple(plan['rp_support']); b = tuple(plan['rp_purlin'])
    for v in (a,b,plan['bolt_axis'],plan['slot_major_axis']):
        if len(v) != 3:
            raise ValueError('Invalid B1 vector')
        for x in v:
            if math.isnan(x) or math.isinf(x):
                raise ValueError('Nonfinite B1 vector')
    delta = sub(b,a)
    if norm(delta) < 1.e-6:
        raise ValueError('Distinct RP centers required')
    axis = unit(plan['bolt_axis']); e1 = unit(delta)
    error = norm(cross(delta,axis))
    if error > 1.e-6 or norm(cross(e1,axis)) > 1.e-6:
        raise ValueError('RP bolt axis coaxial/parallel validation failed')
    major = unit(plan['slot_major_axis'])
    projection = sub(major,scale(e1,dot(major,e1)))
    if norm(projection) < 1.e-8:
        raise ValueError('Slot major axis parallel to bolt axis')
    e2 = unit(projection); e3 = unit(cross(e1,e2))
    return dict(connector_local_1=e1,connector_local_2=e2,connector_local_3=e3,
                coaxial_error_m=error,rp_distance_m=norm(delta))


def b1_probes(center, major, normal, width, length):
    """Capsule boundary samples and outward radial normals; no stored indices."""
    width,length,circular=connector_profile(dict(width_m=width,total_length_m=length))
    r = width/2.; h = (length-width)/2.; minor = unit(cross(normal,major))
    if circular:
        circle=[]
        for index in range(12):
            angle=2.*math.pi*index/12.
            radial=add(scale(major,math.cos(angle)),scale(minor,math.sin(angle)))
            circle.append((add(center,scale(radial,r)),radial))
        return circle
    result = []
    for sign in (-1.,1.):
        for t in (-.75,0.,.75):
            result.append((add(center,add(scale(major,h*t),scale(minor,sign*r))),scale(minor,sign)))
        for theta in (-math.pi/3.,0.,math.pi/3.):
            radial = add(scale(major,sign*math.cos(theta)),scale(minor,math.sin(theta)))
            result.append((add(center,add(scale(major,sign*h),scale(radial,r))),radial))
    return result


def b1_resolve(instance, center, plan, solid):
    major = unit(plan['slot_major_axis']); axis = unit(plan['bolt_axis'])
    if abs(dot(major,axis)) > 1.e-6:
        raise ValueError('Hole axes are not perpendicular')
    probes = b1_probes(center,major,axis,plan['width_m'],plan['total_length_m'])
    selected = {}; hits = 0
    offsets = (0.,)
    if solid:
        if not len(instance.cells):
            raise ValueError('Support is not solid')
        offsets = (-.49*plan['thickness_m'],0.,.49*plan['thickness_m'])
    elif len(instance.cells):
        raise ValueError('Purlin is not shell')
    for point,radial in probes:
        for offset in offsets:
            p = add(point,scale(axis,offset))
            sequence = instance.faces if solid else instance.edges
            item = sequence.findAt((tuple(p),), printWarning=False)
            if item is None:
                raise ValueError('Expected slot boundary missing at '+str(p))
            if not hasattr(item,'getSize'):
                if len(item) != 1:
                    raise ValueError('Ambiguous slot boundary')
                item = item[0]
            if solid:
                n = unit(item.getNormal(point=tuple(p)))
                if dot(n,radial) > -.999:
                    raise ValueError('Expected inward hole-wall normal')
            selected[item.index] = item
            hits += 1
    width,length,circular=connector_profile(plan)
    expected = math.pi*width if circular else 2.*(length-width)+math.pi*width
    if solid:
        expected *= plan['thickness_m']
    measured = 0.
    for item in selected.values():
        measured += item.getSize(printResults=False)
    if abs(measured-expected) > max(1.e-10,expected*1.e-4):
        raise ValueError('Hole region area/perimeter mismatch: '+str(measured))
    # Build an Abaqus GeomSequence from semantic live hits (never fixed indices).
    entities = sequence[0:0]
    for index in sorted(selected.keys()):
        entities += sequence[index:index+1]
    return entities, dict(status='PASS',kind='HOLE_WALL_FACES' if solid else 'SHELL_HOLE_EDGES',
        center_global=center,width_m=plan['width_m'],total_length_m=plan['total_length_m'],
        probe_count=hits,entity_count=len(selected),measured=measured,expected=expected)


def b1_snapshot(model):
    result = {}
    for name in model.parts.keys():
        p = model.parts[name]
        result[name] = dict(features=sorted(p.features.keys()),cells=len(p.cells),faces=len(p.faces),
                            edges=len(p.edges),nodes=len(p.nodes),elements=len(p.elements))
        if len(p.cells):
            result[name]['volume'] = p.getVolume(cells=p.cells)
    return result


def b1_preflight(plan,mdb):
    group = plan['connection_group']
    names = b1_names(group)
    if (group not in ('P01','P02','P03','P04') or plan['connection_family'] != 'PURLIN_BOLT'
            or plan['source_instance'] != 'PURLIN_SUPPORT_'+group[1:]
            or plan['target_instance'] != 'PURLIN_LOCAL_'+group[1:]
            or plan['connector_type'] != 'CARTESIAN' or plan['behavior_status'] != 'PRESET_FOR_WORKFLOW_VALIDATION'
            or not (0. < plan['thickness_m'] < float('inf'))):
        raise ValueError('Unsupported B1 scope')
    connector_profile(plan)
    frame = b1_frame(plan)
    model = resolve_step06_model(mdb, plan['project_id'])
    a = model.rootAssembly
    for key in ('source_instance', 'target_instance'):
        if plan[key] not in a.instances.keys():
            raise ValueError('STEP06_A_REQUIRED: INSTANCE_MISSING: target model missing instance ' + plan[key])
    for repo in (a.features,a.sets,a.surfaces,model.constraints,model.sections):
        for name in names.values():
            if name in repo.keys():
                raise ValueError('EXISTING_STEP06_B_OBJECT: Existing B1 object '+name+'; reopen clean Step06-A CAE')
    regions = []; evidence = []
    from abaqusConstants import ON
    for side,solid in (('source',True),('target',False)):
        instance = a.instances[str(plan[side+'_instance'])]
        if instance.partName != plan[side+'_part']:
            raise ValueError('Instance Part mismatch')
        if instance.dependent != ON:
            raise ValueError('Expected dependent instance')
        center = plan['rp_support'] if solid else plan['rp_purlin']
        try:
            region,check = b1_resolve(instance,center,plan,solid)
        except Exception as error:
            raise ValueError('STEP06_A_REQUIRED: HOLE_REGION_MISSING: ' + str(error))
        regions.append(region); evidence.append(check)
    return model,frame,regions,evidence


def execute_connector_b1(plan,mdb,report_path,prepared=None,shared_section=False):
    from abaqusConstants import ON, OFF, KINEMATIC, WHOLE_SURFACE, UNIFORM, CARTESIAN, IMPRINT
    import part, assembly, interaction, section
    names = b1_names(plan['connection_group'])
    report = dict(plan)
    report.update(status='FAILED',warnings=['PURLIN_BOLT uses a TEMPORARY_PRESET, not final calibrated stiffness.'],
                  errors=[],model_modified=False,created_objects=[])
    report.update(bolt_preset_metadata())
    try:
        model,frame,regions,evidence = prepared if prepared is not None else b1_preflight(plan,mdb)
        report.update(frame); report['model_name'] = model.name
        report['support_region'] = evidence[0]; report['purlin_region'] = evidence[1]
        baseline = b1_snapshot(model)
        a = model.rootAssembly
        previous_constraints = list(model.constraints.keys())
        # All geometry and duplicate preflight is complete before the first mutation.
        name = str(names['connector_section'])
        try:
            if not shared_section:
                model.ConnectorSection(name=name,translationalType=CARTESIAN)
                apply_bolt_preset(model.sections[name])
            else:
                validate_bolt_preset(model.sections[name])
        except Exception as exc:
            if 'behavior' in str(exc).lower():
                raise ValueError('CONNECTOR_BEHAVIOR_REQUIRED: '+str(exc))
            raise ValueError('CONNECTOR_SECTION_CREATION_FAILED (no behavior invented): '+str(exc))
        report['model_modified'] = True
        if not shared_section:
            report['created_objects'].append(name)
        report['connector_section'] = name
        rps = []
        for side,entities,solid in (('support',regions[0],True),('purlin',regions[1],False)):
            name = str(names['rp_'+side])
            feature = a.ReferencePoint(point=tuple(plan['rp_'+side]))
            a.features.changeKey(fromName=str(feature.name),toName=name)
            rp = a.referencePoints[feature.id]; rps.append(rp)
            control = a.Set(name=name,referencePoints=(rp,))
            report['created_objects'].append(name)
            region_name = str(names[side+'_region'])
            surface_name = str(names[side+'_surface'])
            if solid:
                a.Set(name=region_name,faces=entities)
                surface = a.Surface(name=surface_name,side1Faces=entities)
            else:
                a.Set(name=region_name,edges=entities)
                surface = a.Surface(name=surface_name,side1Edges=entities)
            report[side+'_region'].update(name=region_name,surface=surface_name)
            name = str(names[side+'_coupling'])
            model.Coupling(name=name,controlPoint=control,surface=surface,
                influenceRadius=WHOLE_SURFACE,couplingType=KINEMATIC,adjust=OFF,
                localCsys=None,u1=ON,u2=ON,u3=ON,ur1=OFF,ur2=OFF,ur3=OFF,weightingMethod=UNIFORM)
            report[side+'_coupling'] = dict(name=name,type='KINEMATIC',
                dofs=['U1','U2','U3'],released_dofs=['UR1','UR2','UR3'],rotational_transfer='RELEASED')
            report['created_objects'].extend([region_name,surface_name,name])
        wire = a.WirePolyLine(points=((rps[0],rps[1]),),mergeType=IMPRINT,meshable=OFF)
        name = str(names['wire'])
        a.features.changeKey(fromName=str(wire.name),toName=name)
        edges = a.getFeatureEdges(name=name)
        if len(edges) != 1 or abs(edges[0].getSize(printResults=False)-frame['rp_distance_m'])>1.e-6:
            raise ValueError('Expected exactly one RP connector wire')
        region = a.Set(name=name,edges=edges)
        a.SectionAssignment(region=region,sectionName=str(names['connector_section']))
        cs = a.DatumCsysByThreePoints(name=str(names['orientation']),coordSysType=CARTESIAN,
            origin=tuple(plan['rp_support']),point1=add(plan['rp_support'],frame['connector_local_1']),
            point2=add(plan['rp_support'],frame['connector_local_2']))
        a.ConnectorOrientation(region=region,localCsys1=a.datums[cs.id],orient2sameAs1=ON)
        report['wire'] = name; report['orientation'] = names['orientation']
        report['created_objects'].extend([name,names['orientation']])
        a.regenerate()
        for side,solid in (('support',True),('purlin',False)):
            key = 'source_instance' if solid else 'target_instance'
            b1_resolve(a.instances[str(plan[key])],plan['rp_'+side],plan,solid)
            if names[side+'_coupling'] not in model.constraints.keys():
                raise ValueError('Coupling missing after regenerate')
        if len(a.getFeatureEdges(name=str(names['wire']))) != 1:
            raise ValueError('Wire missing after regenerate')
        if baseline != b1_snapshot(model):
            raise ValueError('Part regression snapshot changed')
        for name in previous_constraints:
            if name not in model.constraints.keys():
                raise ValueError('Existing constraint disappeared')
        report['part_regression_status'] = 'PASS'
        report['status'] = 'SUCCESS'
    except Exception as exc:
        report['errors'].append(str(exc))
        if report['model_modified']:
            report['warnings'].append('Partial B1 objects may exist; reopen clean Step06-A CAE before retry.')
        raise
    finally:
        if report_path is not None:
            with open(report_path,'w') as handle:
                json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
    return report
