# HOOP native SOLID round holes. Python 2.7; appended after unchanged Step06-A.
S6H_TOL = 1.e-7
S6H_CONVENTION = 'STEP02_HOOP_INNER_PROFILE_Y0_MATERIAL_POSITIVE_Y'


def s6h_number(value):
    if isinstance(value, bool):
        raise ValueError('Invalid HOOP numeric value')
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError('Nonfinite HOOP numeric value')
    return value


def s6h_face(part, hole, geometry, upper=False):
    center = point3(hole['local_center_m'])
    y = geometry['thickness_m'] if upper else 0.
    origin = (center[0], y, center[2])
    face = part.faces.findAt(coordinates=origin, printWarning=False)
    expected = (0., 1. if upper else -1., 0.)
    if abs(s6_dot(vector3(face.getNormal(point=origin)), expected)-1.) > 1.e-6:
        raise ValueError('HOOP ear face normal mismatch')
    vertices = face.getVertices()
    if not vertices:
        raise ValueError('HOOP planar ear face has no boundary vertices')
    for index in vertices:
        if abs(point3(part.vertices[index])[1]-y) > S6H_TOL:
            raise ValueError('HOOP face is not planar at expected Y')
    radius = hole['diameter_m']/2.
    # The full disk must lie on this same native planar face, not an existing gap.
    for dx, dz in ((radius,0.),(-radius,0.),(0.,radius),(0.,-radius)):
        probe = (center[0]+dx,y,center[2]+dz)
        other = part.faces.findAt(coordinates=probe, printWarning=False)
        if other.index != face.index:
            raise ValueError('HOOP circle crosses an ear face boundary')
    return face, origin


def s6h_prepare(plan, model, report):
    hp = plan['hoop_hole_plan']
    if hp.get('runtime_enabled') is not True or hp.get('coordinate_convention') != S6H_CONVENTION:
        raise ValueError('HOOP runtime not enabled or unsupported coordinate convention')
    assembly = model.rootAssembly
    for feature in assembly.features.values():
        if feature.isSuppressed():
            raise ValueError('Suppressed assembly feature prevents HOOP reference audit')
    for name in model.sketches.keys():
        if str(name).startswith('STEP06_HOOP_'):
            raise ValueError('Existing partial HOOP sketch; reopen clean Step05 model')
    by_part = {}
    seen = set()
    for hole in hp['driving_holes']:
        name, hid = hole['part_name'], hole['hole_id']
        if hid not in ('HOOP_LEFT','HOOP_RIGHT') or (name,hid) in seen:
            raise ValueError('Unknown or duplicate HOOP hole ID')
        seen.add((name,hid))
        by_part.setdefault(name, []).append(hole)
    prepared = []
    for name in sorted(by_part):
        holes = sorted(by_part[name], key=lambda h:h['hole_id'])
        g = hp['part_geometry'][name]
        if g.get('convention') != S6H_CONVENTION or g.get('section_kind') != 'HOOP_BAND' or g.get('model_policy') != 'SOLID':
            raise ValueError('HOOP requires corrected SOLID HOOP_BAND geometry; regenerate Plan')
        for key in ('width_m','thickness_m','left_end_x_m','right_end_x_m','straight_tangent_x_m'):
            s6h_number(g[key])
        w, t, xmin, xmax, tangent = g['width_m'],g['thickness_m'],g['left_end_x_m'],g['right_end_x_m'],g['straight_tangent_x_m']
        if min(w,t,tangent) <= 0. or xmin >= -tangent or xmax <= tangent:
            raise ValueError('Invalid HOOP straight plate geometry')
        part = resolve_repository_item(model.parts,name,'HOOP Part')
        if not len(part.cells):
            raise ValueError('HOOP must be a native solid with cells')
        for key in part.features.keys():
            if str(key).startswith(('STEP06_HOLE_HOOP_','STEP06_HOOP_')):
                raise ValueError('Existing HOOP features; reopen clean Step05 model before rerun')
        points = []
        for vertex in part.vertices:
            points.append(point3(vertex))
        if not points:
            raise ValueError('Missing HOOP native geometry')
        for dimension,low,high in ((0,xmin,xmax),(2,0.,w)):
            values = []
            for point in points:
                values.append(point[dimension])
            if abs(min(values)-low)>S6H_TOL or abs(max(values)-high)>S6H_TOL:
                raise ValueError('HOOP actual X/Z extents differ from Plan')
        for point in points:
            if point[1] < -S6H_TOL:
                raise ValueError('HOOP uses obsolete negative-Y geometry')
        refs = holes[0]['shared_part_info']['referencing_instances']
        if not refs or len(set(refs)) != len(refs):
            raise ValueError('Invalid HOOP reference evidence')
        refs = s6a_references(assembly,part,refs)
        execution = 'MODIFY_SHARED_PART_ONCE' if len(refs)>1 else 'MODIFY_PART_ONCE'
        entry = dict(status='PREFLIGHT',part_name=name,referencing_instances=refs,
                     shared_part=len(refs)>1,execution_policy=execution,
                     mesh_removed=False,remesh_required=False,created_holes=0,holes=[],
                     mesh_nodes_before=len(part.nodes),mesh_elements_before=len(part.elements),
                     volume_before=s6_volume(part),expected_removed_volume=0.,model_modified=False,
                     created_auxiliary_features=[],instance_inheritance=[])
        report['parts'].append(entry)
        for hole in holes:
            center = point3(hole['local_center_m'])
            for value in center:
                s6h_number(value)
            diameter = s6h_number(hole['diameter_m'])
            radius = diameter/2.
            if hole['hole_type']!='ROUND' or diameter<=0. or tuple(hole['local_axis'])!=(0.,1.,0.):
                raise ValueError('HOOP supports ROUND with local +Y axis only')
            if abs(center[1]-t/2.)>S6H_TOL:
                raise ValueError('HOOP center must be at mid-thickness')
            left = hole['hole_id']=='HOOP_LEFT'
            if hole['end_reference'] != ('LEFT' if left else 'RIGHT'):
                raise ValueError('HOOP Part-local end reference mismatch')
            low,high = (xmin,-tangent) if left else (tangent,xmax)
            if center[0]-radius<=low+S6H_TOL or center[0]+radius>=high-S6H_TOL or center[2]-radius<=S6H_TOL or center[2]+radius>=w-S6H_TOL:
                raise ValueError('HOOP circle crosses free edge / width edge / transition fillet / arc')
            info = hole['shared_part_info']
            if sorted(info['referencing_instances'])!=refs or sorted(info['expected_affected_instances'])!=refs or info['part_name']!=name or info['requires_instance_isolation'] or not info['hole_pattern_identical'] or info['execution_policy']!=execution:
                raise ValueError('HOOP shared Part pattern evidence mismatch')
            s6h_face(part,hole,g)
            s6h_face(part,hole,g,upper=True)
            entry['expected_removed_volume'] += math.pi*diameter*diameter/4.*t
        if entry['expected_removed_volume'] >= entry['volume_before']:
            raise ValueError('HOOP removal exceeds solid volume')
        entry['status'] = 'PREFLIGHT_PASSED'
        prepared.append((part,holes,g,entry))
    report['status'] = 'PREFLIGHT_PASSED'
    return prepared


def s6h_post_geometry(part, holes, g, entry):
    """Positive native cylindrical-wall evidence, independent of feature metadata.

    Sample each planned radius at four angles and three depths, require inward
    radial normals, and sum unique wall-face areas. A blind/short bore cannot
    provide the full 2*pi*r*T wall area; a misplaced bore cannot match probes.
    """
    entry['cut_geometry_status'] = 'FAIL'
    entry['volume_validation'] = 'FAIL'
    if not len(part.cells):
        raise ValueError('HOOP geometry invalid after regenerate: no solid cells')
    after = s6_volume(part)
    expected = entry['expected_removed_volume']
    if abs(entry['volume_before']-after-expected)>max(expected*1.e-4,1.e-12):
        raise ValueError('HOOP removed volume changed after regenerate')
    entry['volume_validation'] = 'PASS'
    entry['post_regenerate_volume'] = after
    entry['geometry_checks'] = []
    for hole in holes:
        center = hole['local_center_m']
        radius = hole['diameter_m']/2.
        walls = {}
        for fraction in (.001,.5,.999):
            # Avoid the sketch circle's usual cardinal seam while sampling all quadrants.
            q = math.sqrt(.5)
            for dx,dz in ((q,q),(-q,q),(-q,-q),(q,-q)):
                probe = (center[0]+radius*dx,g['thickness_m']*fraction,center[2]+radius*dz)
                face = part.faces.findAt(coordinates=probe,printWarning=False)
                if face is None:
                    raise ValueError('HOOP cylindrical wall missing at planned hole: '+hole['hole_id'])
                normal = vector3(face.getNormal(point=probe))
                if abs(s6_dot(normal,(-dx,0.,-dz))-1.)>1.e-5:
                    raise ValueError('HOOP bore wall normal mismatch: '+hole['hole_id'])
                walls[face.index] = face
        area = 0.
        for face in walls.values():
            area += s6h_number(face.getSize(printResults=False))
        expected_area = 2.*math.pi*radius*g['thickness_m']
        if abs(area-expected_area)>max(expected_area*1.e-4,1.e-12):
            raise ValueError('HOOP through-thickness cylindrical wall area mismatch: '+hole['hole_id'])
        entry['geometry_checks'].append(dict(hole_id=hole['hole_id'],status='PASS',
            wall_probe_count=12,wall_area=area,expected_wall_area=expected_area))
    entry['cut_geometry_status'] = 'PASS'


def s6h_feature_evidence(part, names, entry):
    entry['feature_repository_status'] = 'FOUND'
    entry['feature_evidence'] = []
    for name in names:
        evidence = dict(feature_name=name,feature_status='NOT_CONFIRMED_AFTER_REGENERATE')
        try:
            feature = part.features[abaqus_name(name)]
        except Exception as exc:
            evidence['diagnostic'] = str(exc)
            entry['warnings'].append('HOOP cut feature repository entry not found after regenerate; geometry validation passed.')
        else:
            evidence['feature_status'] = 'FOUND'
            try:
                if feature.isSuppressed():
                    evidence['suppression_status'] = 'REPORTED_SUPPRESSED'
                    entry['warnings'].append('HOOP feature reported suppressed after regenerate; geometry validation passed.')
                else:
                    evidence['suppression_status'] = 'NOT_SUPPRESSED'
            except Exception as exc:
                evidence['suppression_status'] = 'UNAVAILABLE'
                evidence['diagnostic'] = str(exc)
                entry['warnings'].append('HOOP feature suppression status unavailable after regenerate; geometry validation passed.')
        if evidence['feature_status']!='FOUND' or evidence.get('suppression_status')!='NOT_SUPPRESSED':
            entry['feature_repository_status'] = 'NOT_CONFIRMED_AFTER_REGENERATE'
        entry['feature_evidence'].append(evidence)


def s6h_execute(model, prepared, report):
    from abaqusConstants import OFF, SIDE1, RIGHT, ZAXIS
    report['status'] = 'EXECUTING'
    for part,holes,g,entry in prepared:
        entry['status'] = 'EXECUTING'
        if len(part.nodes) or len(part.elements):
            entry['model_modified'] = True
            entry['remesh_required'] = True
            part.deleteMesh()
            entry['mesh_removed'] = not len(part.nodes) and not len(part.elements)
            if not entry['mesh_removed']:
                raise ValueError('HOOP mesh remains after deleteMesh')
        for hole in holes:
            face,origin = s6h_face(part,hole,g)
            # Reacquire Face after each topology mutation; never cache face indices.
            entry['model_modified'] = True
            entry['remesh_required'] = True
            datum = part.DatumAxisByPrincipalAxis(principalAxis=ZAXIS)
            datum_name = 'STEP06_HOOP_AXIS_'+hole['hole_id']
            part.features.changeKey(fromName=abaqus_name(datum.name),toName=abaqus_name(datum_name))
            entry['created_auxiliary_features'].append(datum_name)
            up = part.datums[datum.id]
            matrix = part.MakeSketchTransform(sketchPlane=face,sketchUpEdge=up,sketchPlaneSide=SIDE1,
                                             sketchOrientation=RIGHT,origin=origin).matrix()
            if len(matrix)!=12:
                raise ValueError('Unexpected HOOP sketch transform')
            for i in range(3):
                if abs(matrix[9+i]-origin[i])>S6H_TOL:
                    raise ValueError('HOOP sketch origin mismatch')
            if abs(s6_dot(matrix[6:9],(0.,-1.,0.))-1.)>1.e-6:
                raise ValueError('HOOP sketch normal mismatch')
            sketch_name = 'STEP06_HOOP_SKETCH_'+hole['hole_id']
            sketch = model.ConstrainedSketch(name=abaqus_name(sketch_name),sheetSize=1.,transform=matrix)
            sketch.CircleByCenterPerimeter(center=(0.,0.),point1=(hole['diameter_m']/2.,0.))
            before = s6_volume(part)
            feature = part.CutExtrude(sketchPlane=face,sketchPlaneSide=SIDE1,sketchUpEdge=up,
                                     sketchOrientation=RIGHT,sketch=sketch,flipExtrudeDirection=OFF,
                                     depth=g['thickness_m'])
            feature_name = 'STEP06_HOLE_'+hole['hole_id']
            part.features.changeKey(fromName=abaqus_name(feature.name),toName=abaqus_name(feature_name))
            removed = before-s6_volume(part)
            expected = math.pi*hole['diameter_m']**2/4.*g['thickness_m']
            entry['holes'].append(dict(hole_id=hole['hole_id'],local_center=hole['local_center_m'],
                local_axis=hole['local_axis'],diameter=hole['diameter_m'],feature_name=feature_name,
                removed_volume=removed,expected_removed_volume=expected))
            entry['created_holes'] = len(entry['holes'])
            if abs(removed-expected)>max(expected*1.e-4,1.e-12):
                raise ValueError('HOOP cut volume mismatch; inspect partial model, no automatic retry')
            del model.sketches[abaqus_name(sketch_name)]
        entry['volume_after'] = s6_volume(part)
        entry['removed_volume'] = entry['volume_before']-entry['volume_after']
        expected = entry['expected_removed_volume']
        if abs(entry['removed_volume']-expected)>max(expected*1.e-4,1.e-12):
            raise ValueError('HOOP total removed volume mismatch')
        entry['status'] = 'CUT_COMPLETE'
    model.rootAssembly.regenerate()
    for part,holes,g,entry in prepared:
        entry.update(warnings=[],assembly_inheritance_status='FAIL')
        s6h_post_geometry(part,holes,g,entry)
        refs = s6a_references(model.rootAssembly,part,entry['referencing_instances'])
        names = []
        for hole in holes:
            name = 'STEP06_HOLE_'+hole['hole_id']
            names.append(name)
        s6h_feature_evidence(part,names,entry)
        for name in refs:
            entry['instance_inheritance'].append(dict(instance_name=name,part_name=part.name,
                feature_names=names,status='DEPENDENT_PART_REFERENCE_VERIFIED'))
        entry['assembly_inheritance_status'] = 'PASS'
        entry['status'] = 'SUCCESS'
    for key in ('cut_geometry_status','volume_validation','assembly_inheritance_status'):
        report[key] = 'PASS'
    report['feature_repository_status'] = 'FOUND'
    report['warnings'] = []
    for part,holes,g,entry in prepared:
        report['warnings'].extend(entry['warnings'])
        if entry['feature_repository_status']!='FOUND':
            report['feature_repository_status']='NOT_CONFIRMED_AFTER_REGENERATE'
    report['status'] = 'SUCCESS'


def execute_step06_with_hoop(plan, mdb, report_path, fingerprint):
    """Preflight HOOP before any mutations, then run unchanged Step06-A and HOOP last."""
    hoop = dict(status='PREFLIGHT',parts=[],created_holes=0,errors=[])
    report = dict(project_id=plan['project_id'],status='PREFLIGHT',model_modified=False,
                  created_holes=0,errors=[],plan_fingerprint=fingerprint)
    base_started, base_finished = False, False
    try:
        model = resolve_repository_item(mdb.models,plan['project_id'],'Model')
        prepared = s6h_prepare(plan,model,hoop)
        base_started = True
        report = execute_step06_a(plan,mdb,report_path,fingerprint)
        base_finished = True
        report['status'] = 'EXECUTING_HOOP'
        report['hoop_validation'] = hoop
        with open(report_path,'w') as handle:
            json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
        s6h_execute(model,prepared,hoop)
        report['status'] = 'SUCCESS'
        return report
    except Exception as exc:
        if base_started and not base_finished:
            # The unchanged executor already wrote its detailed partial-failure report.
            with open(report_path,'r') as handle:
                report = json.load(handle)
            hoop['status'] = 'NOT_EXECUTED_BASE_FAILED'
        else:
            hoop['status'] = 'FAILED'
            hoop['errors'].append(str(exc))
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        for key in ('cut_geometry_status','volume_validation','assembly_inheritance_status'):
            states = []
            for entry in hoop['parts']:
                states.append(entry.get(key,'NOT_CHECKED'))
            all_pass = bool(states)
            for state in states:
                if state != 'PASS':
                    all_pass = False
            hoop[key] = 'FAIL' if 'FAIL' in states else ('PASS' if all_pass else 'NOT_CHECKED')
        for entry in hoop['parts']:
            hoop['created_holes'] += entry['created_holes']
            if entry['model_modified']:
                report['model_modified'] = True
            for flag,key in (('mesh_removed','mesh_removed_parts'),('remesh_required','remesh_required_parts')):
                if entry[flag]:
                    report.setdefault(key,[]).append(entry['part_name'])
            if hoop['status']=='FAILED' and entry['status'] in ('EXECUTING','CUT_COMPLETE'):
                entry['status']='FAILED'
        if len(hoop['parts'])==1:
            for key,value in hoop['parts'][0].items():
                if key not in ('status','created_holes'):
                    hoop[key]=value
        report['hoop_validation'] = hoop
        report['created_holes'] = report.get('created_holes',0)+hoop['created_holes']
        with open(report_path,'w') as handle:
            json.dump(report,handle,indent=2,ensure_ascii=True,allow_nan=False)
