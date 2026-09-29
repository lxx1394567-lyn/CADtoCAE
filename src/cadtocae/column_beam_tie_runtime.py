"""CAE 2020 shell column/beam contact selection; shared by front and rear."""


def cbt_contact_pair(beam, beam_ids, column, column_ids):
    scores = []
    for bi in beam_ids:
        bf = beam.faces[bi]
        bn = normal(bf)
        bc = point3(bf.getCentroid())
        for ci in column_ids:
            cf = column.faces[ci]
            cn = normal(cf)
            if abs(dot(bn,cn)) < 1.-1.e-5:
                continue
            cc = point3(cf.getCentroid())
            delta = sub(cc,bc)
            gap = abs(dot(delta,bn))
            distance = math.sqrt(dot(delta,delta))
            scores.append((gap,distance,bi,ci))
    if not scores:
        raise ValueError('COLUMN_BEAM_TIE no normal-compatible contact face')
    scores.sort()
    nearest = []
    for score in scores:
        if abs(score[0]-scores[0][0]) < 1.e-6:
            nearest.append(score)
    nearest.sort(key=lambda value:value[1])
    if len(nearest)>1 and abs(nearest[0][1]-nearest[1][1])<1.e-6:
        raise ValueError('COLUMN_BEAM_TIE contact face ambiguous')
    return nearest[0]


def cbt_contact_side(face, other, own_reference=None, other_reference=None):
    # Same physical-direction principle as OUTER/INNER: the shell normal must
    # face toward the opposing contact surface. Never choose an arbitrary side.
    direction = sub(point3(other.getCentroid()),point3(face.getCentroid()))
    signed = dot(normal(face),direction)
    if abs(signed)<1.e-9 and own_reference is not None and other_reference is not None:
        # Coplanar shell webs can still have a unique contact direction when
        # their C-section limbs lie on opposite sides of the common plane.
        anchor = point3(face.getCentroid())
        own = dot(normal(face),sub(own_reference,anchor))
        opposing = dot(normal(face),sub(other_reference,anchor))
        if own*opposing < -1.e-18:
            signed = opposing-own
    if abs(signed)<1.e-9:
        raise ValueError('COLUMN_BEAM_TIE physical side ambiguous: coincident midsurfaces')
    return 'SIDE1' if signed>0. else 'SIDE2'


def cbt_write(path,report):
    with open(path) as handle:
        combined = json.load(handle)
    combined['column_beam_tie'] = report
    if report['status']=='FAILED': combined['overall_status'] = 'FAILED'
    with open(path,'w') as handle:
        json.dump(combined,handle,ensure_ascii=True,indent=2)


def execute_column_beam(plan,mdb,path,ON,COMPUTED,tie_batch):
    report = dict(rule_id='COLUMN_BEAM_TIE',status='PREFLIGHT',connections=[],
                  semantic_mapping={},errors=[],material_removed=False)
    try:
        model = item(mdb.models,plan['model_name'])
        a = model.rootAssembly
        rule = plan['column_beam_tie']
        for c in rule['connections']:
            bp = item(model.parts,c['beam_part'])
            cp = item(model.parts,c['column_part'])
            bi = item(a.instances,c['beam'])
            ci = item(a.instances,c['column'])
            for part,inst in ((bp,bi),(cp,ci)):
                if len(part.faces)!=len(inst.faces):
                    raise ValueError('COLUMN_BEAM_TIE Part/Instance face correspondence differs')
                for face in part.faces:
                    if tuple(face.getVertices())!=tuple(inst.faces[face.index].getVertices()):
                        raise ValueError('COLUMN_BEAM_TIE Part/Instance face correspondence differs')
            beam_candidates = zone_faces(bp,c['beam_range'])
            column_candidates = zone_faces(cp,c['column_range'])
            gap,distance,bid,cid = cbt_contact_pair(bi,beam_candidates,ci,column_candidates)
            beam_centers = []
            column_centers = []
            for index in beam_candidates:
                beam_centers.append(point3(bi.faces[index].getCentroid()))
            for index in column_candidates:
                column_centers.append(point3(ci.faces[index].getCentroid()))
            beam_reference = center(beam_centers)
            column_reference = center(column_centers)
            beam_side = cbt_contact_side(bi.faces[bid],ci.faces[cid],beam_reference,column_reference)
            column_side = cbt_contact_side(ci.faces[cid],bi.faces[bid],column_reference,beam_reference)
            master = region(a,c['column_region'],seq(ci.faces,[cid]),column_side,report)
            slave = region(a,c['beam_region'],seq(bi.faces,[bid]),beam_side,report)
            master_name = abaqus_name(c['column_region'].replace('REGION_','SURF_'))
            slave_name = abaqus_name(c['beam_region'].replace('REGION_','SURF_'))
            tie_name = abaqus_name(c['tie'])
            old = item(model.constraints,tie_name,True)
            if old is not None:
                if surface_key(a,old.master)!=master_name or surface_key(a,old.slave)!=slave_name or old.positionToleranceMethod!=COMPUTED or old.adjust!=ON or old.tieRotations!=ON or old.thickness!=ON or getattr(old,'suppressed',False) or str(getattr(old,'constraintEnforcement','SOLVER_DEFAULT'))!='SOLVER_DEFAULT' or str(getattr(old,'constraintRatioMethod','DEFAULT'))!='DEFAULT':
                    raise ValueError('Conflicting COLUMN_BEAM_TIE '+tie_name)
            tie_batch.stage(model,master_surface_name=master_name,slave_surface_name=slave_name,
                master_instance=c['column'],slave_instance=c['beam'],name=tie_name,master=master,slave=slave,
                positionToleranceMethod=COMPUTED,adjust=ON,tieRotations=ON,thickness=ON)
            record = dict(c,beam_candidate_faces=beam_candidates,column_candidate_faces=column_candidates,
                beam_faces=[bid],column_faces=[cid],beam_side=beam_side,column_side=column_side,
                beam_section_reference=beam_reference,column_section_reference=column_reference,
                normal_gap_m=gap,center_distance_m=distance,created=False)
            report['connections'].append(record)
            print('COLUMN_BEAM_TIE %s column physical side = %s; beam physical side = %s' % (c['id'],column_side,beam_side))
            print(json.dumps(record,sort_keys=True))
        report['status'] = 'PENDING_TIE_PREFLIGHT'
    except Exception as exc:
        report['status'] = 'FAILED'
        report['errors'].append(str(exc))
        raise
    finally:
        cbt_write(path,report)
