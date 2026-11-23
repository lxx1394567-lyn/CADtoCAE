# -*- coding: utf-8 -*-
"""User-confirmed hoop/brace regions: brace web end 50 mm; outer bolt +/-10 mm."""
def s8_rectangle(pair,points,normal):
    origin=points[0];u,v=t4_frame(normal);poly=t4_hull([[t4_dot(t4_sub(q,origin),a) for a in (u,v)] for q in points])
    return dict(solid=pair['solid'],shell=pair['shell'],origin=origin,normal=normal,u=u,v=v,polygon=poly,outer_area=t4_area(poly),gap_m=0.,shell_thickness=0.,shell_offset=0.,shell_side=pair['patches'][0]['shell_side'])

def s8_user_hoop_brace(m,c,pair):
    rows={}
    for row in c['summary']['instances']:rows[str(row['instance_name'])]=row
    hoop=rows[pair['solid']];brace=rows[pair['shell']];a=m.rootAssembly;hi=a.instances[pair['solid']];bi=a.instances[pair['shell']];hp=m.parts[hi.partName];bp=m.parts[bi.partName]
    contact=pair['patches'][0];local_contact=step04_global_point_to_local(contact['origin'],hoop['placement']);patterns=[]
    for entry in c['hole_report'].get('hoop_validation',{}).get('part_patterns',[]):
        if pair['solid'] in entry.get('referencing_instances',[]):patterns+=entry['hole_pattern']
    candidates=[x for x in patterns if x['local_center'][0]*local_contact[0]>0]
    if not candidates:raise ValueError('OUTER_HOOP_HOLE_NOT_IDENTIFIED: '+pair['solid'])
    outer=max([abs(x['local_center'][0]) for x in candidates]);holes=[x for x in candidates if abs(abs(x['local_center'][0])-outer)<2.e-6]
    low=min([v.pointOn[0][2] for v in hp.vertices]);high=max([v.pointOn[0][2] for v in hp.vertices]);solid_patches=[]
    for hole in holes:
        x=hole['local_center'][0];y=local_contact[1]
        points=[step04_local_point_to_global((xx,y,zz),hoop['placement']) for xx,zz in [(x-.01,low),(x+.01,low),(x+.01,high),(x-.01,high)]]
        solid_patches.append(s8_rectangle(pair,points,contact['normal']))
    # Identify the web by local plane/normal, not persistent Face IDs.
    web=[]
    for f in bp.faces:
        n=f.getNormal(point=f.pointOn[0])
        if abs(abs(n[0])-1.)<1.e-6 and abs(f.pointOn[0][0])<2.e-6:web.append(f)
    if not web:raise ValueError('BRACE_WEB_PLANE_UNRESOLVED')
    points=[bp.vertices[k].pointOn[0] for f in web for k in f.getVertices()];y0=min([q[1] for q in points]);y1=max([q[1] for q in points]);z0=min([q[2] for q in points]);z1=max([q[2] for q in points])
    samples=[]
    for patch in pair['patches']:
        for q in patch['polygon']:
            g=[patch['origin'][k]+q[0]*patch['u'][k]+q[1]*patch['v'][k] for k in range(3)];samples.append(step04_global_point_to_local(g,brace['placement'])[2])
    center=sum(samples)/len(samples);end='FRONT' if abs(center-z0)<abs(center-z1) else 'REAR'
    if z1-z0<.05:raise ValueError('BRACE_TOO_SHORT_FOR_50MM_REGION')
    lo=z0 if end=='FRONT' else z1-.05;up=z0+.05 if end=='FRONT' else z1
    corners=[step04_local_point_to_global((0.,y,z),brace['placement']) for y,z in [(y0,lo),(y1,lo),(y1,up),(y0,up)]]
    pair['selection_patches']=dict(solid=solid_patches,shell=[s8_rectangle(pair,corners,contact['normal'])])
    pair['region_rule']=dict(name='USER_CONFIRMED_BRACE_50MM_HOOP_OUTER_HOLE_PLUS_MINUS_10MM',brace_end=end,brace_length_m=.05,hoop_hole_ids=[x['hole_id'] for x in holes],hoop_half_width_m=.01,hoop_height_m=high-low,strict_overlap_required=False,confirmation='User 2026-11-01 confirmed hole-centre +/-10 mm, full outer-face height')
    return pair
