"""Project-specific, user-confirmed support layout; never infer from structure type."""
import copy
import math

CONFIRMED_LAYOUTS = {
    'DP_ANG14_FA03521S-T0104-02': dict(
        project_id='DP_ANG14_FA03521S-T0104-02', model_id='M07', structure_type='DP',
        purlin_length_m=8.058, support_count=3, support_spacing_m=[3.700,3.700],
        support_position='MIDDLE', support_index=1,
        cantilever_left_m=.329, cantilever_right_m=.329,
        source='User-confirmed 2x7 layout, 2026-10-20; drawing overall 8058 mm takes precedence',
        pending_confirmation='Drawing cantilevers 429 mm conflict with 8058 mm; assumed 329 mm each')
}

def tributary_layout(project,model,structure,layout=None):
    d=copy.deepcopy(layout if layout is not None else CONFIRMED_LAYOUTS.get(project))
    if d is None:raise ValueError('SUPPORT_LAYOUT_REQUIRED: '+project)
    if (d['project_id'],d['model_id'],d['structure_type'])!=(project,model,structure):raise ValueError('SUPPORT_LAYOUT_IDENTITY_MISMATCH')
    if structure not in ('SP_SC','SP_DC','DP'):raise ValueError('UNKNOWN_STRUCTURE_TYPE')
    n=d['support_count'];spacing=d['support_spacing_m'];left=d['cantilever_left_m'];right=d['cantilever_right_m'];length=d['purlin_length_m'];index=d['support_index']
    if not isinstance(n,int) or isinstance(n,bool) or n<1 or len(spacing)!=n-1:raise ValueError('SUPPORT_COUNT_SPACING_MISMATCH')
    if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<n:raise ValueError('SUPPORT_INDEX_INVALID')
    if any(not math.isfinite(x) or x<0 for x in [left,right,length]+spacing) or length<=0 or any(x<=0 for x in spacing):raise ValueError('SUPPORT_LAYOUT_LENGTH_INVALID')
    if not math.isclose(left+sum(spacing)+right,length,abs_tol=1e-8,rel_tol=0):raise ValueError('SUPPORT_LAYOUT_LENGTH_SUM_MISMATCH')
    spans=[length] if n==1 else [left+spacing[0]/2]+[(spacing[k-1]+spacing[k])/2 for k in range(1,n-1)]+[right+spacing[-1]/2]
    position='SINGLE' if n==1 else ('LEFT' if index==0 else ('RIGHT' if index==n-1 else 'MIDDLE'))
    if d['support_position']!=position:raise ValueError('SUPPORT_POSITION_INDEX_MISMATCH')
    if any(x<=0 for x in spans) or not math.isclose(sum(spans),length,abs_tol=1e-8,rel_tol=0):raise ValueError('TRIBUTARY_SUM_MISMATCH')
    d.update(tributary_lengths_m=spans,tributary_length_m=spans[index],distribution_rule='half adjacent spans plus end cantilever')
    return d
