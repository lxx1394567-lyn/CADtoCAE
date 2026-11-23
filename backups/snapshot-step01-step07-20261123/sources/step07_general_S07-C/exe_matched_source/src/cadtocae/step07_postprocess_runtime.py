# -*- coding: utf-8 -*-
"""Stage07 read-only ODB extraction and visualization; Abaqus Python 2.7."""
import os, json, hashlib, traceback, datetime, math, zipfile
from xml.sax.saxutils import escape

def pp_api(value):
    # Abaqus 2020 kernel string arguments reject Python 2 unicode.
    try:
        if isinstance(value,unicode):return value.encode('mbcs')
    except NameError:pass
    return value

def pp_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            b=f.read(1024*1024)
            if not b:break
            h.update(b)
    return h.hexdigest()

def pp_json(path,value):
    with open(path,'w') as f:json.dump(value,f,indent=2,ensure_ascii=True,allow_nan=False)

def pp_new_dir(root,job):
    if not os.path.isdir(root):os.makedirs(root)
    n=1
    while True:
        p=os.path.join(root,job+('' if n==1 else '_v%d'%n))
        try:os.mkdir(p);return p
        except OSError:
            if not os.path.isdir(p):raise
            n+=1

def pp_peak(values,odb):
    from abaqusConstants import INTEGRATION_POINT
    best=None;count=0
    for v in values:
        if v.position != INTEGRATION_POINT:continue
        x=float(v.mises)
        if math.isnan(x) or math.isinf(x):raise ValueError('NONFINITE_STRESS')
        count+=1
        if best is None or x>best[0]:best=(x,v)
    if best is None:raise ValueError('NO_RAW_INTEGRATION_POINT_STRESS')
    x,v=best;inst=v.instance;el=inst.getElementFromLabel(v.elementLabel)
    sp=getattr(v,'sectionPoint',None)
    return dict(mises_MPa=x/1e6,instance=inst.name,element_label=v.elementLabel,
                integration_point=v.integrationPoint,section_point=str(sp),element_type=el.type,
                integration_point_coordinates=None,coordinate_status='NOT_AVAILABLE_IN_ODB_NO_COORD_FIELD',
                sample_count=count,safety_factor='PENDING_MATERIAL_STRENGTH')

def pp_base_rf(o,f,c):
    # Exact Stage03 RP sets only; do not sum all constrained nodes or coupling aliases.
    project=c['project_id']
    expected=(['STEP07_RP_BASE_FRONT','STEP07_RP_BASE_REAR'] if project.startswith('DP_') else
              ['STEP07_RP_BASE'] if project.startswith(('SP_SC_','SP_DC_')) else [])
    result=dict(status='REVIEW_REQUIRED',unit='N',coordinate_system='GLOBAL',expected_sets=expected,
                rows=[],total_components_N=None,total_magnitude_N=None,issues=[])
    if not expected:result['issues'].append('UNKNOWN_STRUCTURE_TYPE');return result
    if 'RF' not in f.fieldOutputs:result['issues'].append('RF_FIELD_MISSING');return result
    repo=o.rootAssembly.nodeSets;names={str(n).upper():n for n in repo.keys()};seen=set()
    for name in expected:
        if name not in names:result['issues'].append('BASE_RP_SET_MISSING: '+name);continue
        region=repo[names[name]];count=0
        for seq in region.nodes:count+=1 if hasattr(seq,'label') else len(seq)
        if count!=1:result['issues'].append('BASE_RP_SET_NOT_SINGLE_NODE: '+name);continue
        values=list(f.fieldOutputs['RF'].getSubset(region=region).values)
        if len(values)!=1:result['issues'].append('BASE_RF_VALUE_COUNT: '+name);continue
        v=values[0];instance=v.instance.name if v.instance else 'ASSEMBLY';key=(instance,int(v.nodeLabel))
        if key in seen:result['issues'].append('DUPLICATE_BASE_NODE: '+name);continue
        seen.add(key)
        try:data=v.data;local=v.localCoordSystem
        except Exception:data=v.dataDouble;local=v.localCoordSystemDouble
        if local is not None:result['issues'].append('LOCAL_RF_REQUIRES_TRANSFORM: '+name);continue
        data=[float(x) for x in data]
        if len(data)!=3 or any(math.isnan(x) or math.isinf(x) for x in data):
            result['issues'].append('INVALID_RF_VECTOR: '+name);continue
        result['rows'].append(dict(set=name,instance=instance,node_label=int(v.nodeLabel),
                                   components_N=data,magnitude_N=math.sqrt(sum([x*x for x in data]))))
    if not result['issues'] and len(result['rows'])==len(expected):
        total=[sum([row['components_N'][i] for row in result['rows']]) for i in range(3)]
        result.update(status='SUCCESS',total_components_N=total,total_magnitude_N=math.sqrt(sum([x*x for x in total])))
    return result

def pp_extract(o,c):
    from abaqusConstants import INTEGRATION_POINT
    status=str(o.diagnosticData.jobStatus)
    if status!='JOB_STATUS_COMPLETED_SUCCESSFULLY':raise ValueError('CALCULATION_NOT_COMPLETED: '+status)
    keys=list(o.steps.keys());key=c['step'] or keys[-1]
    if key not in o.steps:raise ValueError('STEP_NOT_FOUND: '+key)
    st=o.steps[key];index=c['frame']
    if index==-1:
        valid=[i for i,f in enumerate(st.frames) if 'S' in f.fieldOutputs and 'U' in f.fieldOutputs]
        if not valid:raise ValueError('NO_VALID_S_U_FRAME')
        index=valid[-1]
    if index<0 or index>=len(st.frames):raise ValueError('FRAME_OUT_OF_RANGE')
    f=st.frames[index]
    if 'S' not in f.fieldOutputs or 'U' not in f.fieldOutputs:raise ValueError('S_OR_U_MISSING')
    names={n.upper():n for n in o.rootAssembly.instances.keys()}
    missing=[n for n in c['expected_instances'] if n.upper() not in names]
    if missing:raise ValueError('ODB_ASSEMBLY_MISMATCH: '+str(missing))
    s=f.fieldOutputs['S']
    if not any(loc.position==INTEGRATION_POINT for loc in s.locations):raise ValueError('NO_RAW_IP_S')
    global_s=pp_peak(s.values,o)
    uv=max(f.fieldOutputs['U'].values,key=lambda v:float(v.magnitude))
    u=dict(magnitude_mm=float(uv.magnitude)*1000,instance=uv.instance.name,node_label=uv.nodeLabel,
           components_mm=[float(x)*1000 for x in uv.data])
    if not all(not math.isnan(x) and not math.isinf(x) for x in [u['magnitude_mm']]+u['components_mm']):raise ValueError('NONFINITE_U')
    r=dict(status='EXTRACTED',calculation_status=status,step=key,frame=index,step_time=f.frameValue,
           global_stress=global_s,global_displacement=u,supports=[],hoops=[],mapping=[],
           available_steps=[dict(name=k,frames=[dict(index=i,time=x.frameValue,fields=list(x.fieldOutputs.keys())) for i,x in enumerate(o.steps[k].frames)]) for k in keys])
    for kind in ('supports','hoops'):
        for group,members in sorted(c['groups'][kind].items()):
            peaks=[];actual=[]
            for member in members:
                name=names[member.upper()];inst=o.rootAssembly.instances[name]
                peak=pp_peak(s.getSubset(region=inst,position=INTEGRATION_POINT,readOnly=True).values,o)
                peaks.append(peak);actual.append(name)
                r['mapping'].append(dict(summary_instance=member,odb_instance=name,category=kind,group=group,
                                         nodes=len(inst.nodes),elements=len(inst.elements),element_types=sorted(set(e.type for e in inst.elements))))
            peak=dict(max(peaks,key=lambda p:p['mises_MPa']));peak.update(group=group,instances=actual,member_peaks=peaks)
            r[kind].append(peak)
    r['base_reaction']=pp_base_rf(o,f,c)
    r['controlling_support']=max(r['supports'],key=lambda p:p['mises_MPa'])['group']
    r['controlling_hoop']=max(r['hoops'],key=lambda p:p['mises_MPa'])['group']
    r['warnings']=[]
    for owner in [o.rootAssembly]+list(o.rootAssembly.instances.values()):
        for repo in ('nodeSets','elementSets'):
            for name,obj in getattr(owner,repo).items():
                if 'WARN' in name.upper() or 'ERR' in name.upper():
                    seq=obj.nodes if repo=='nodeSets' else obj.elements
                    count=0
                    for x in seq:count+=len(x) if not hasattr(x,'label') else 1
                    r['warnings'].append(dict(owner=getattr(owner,'name','ASSEMBLY'),set=name,kind=repo,count=count))
    r['solver_warnings']=o.diagnosticData.numberOfAnalysisWarnings
    r['solver_errors']=o.diagnosticData.numberOfAnalysisErrors
    # Preserve actual solver diagnostics, not warning counts from a different historical job.
    dat=os.path.splitext(c['odb'])[0]+'.dat'
    if os.path.isfile(dat):
        lines=open(dat,'r').readlines();r['dat_warning_excerpts']=[ ''.join(lines[max(0,i-1):i+5]).strip() for i,line in enumerate(lines) if '***WARNING' in line or '***ERROR' in line]
    else:r['dat_warning_excerpts']=['MATCHING_DAT_NOT_AVAILABLE']
    r['engineering_acceptance']='NOT_EVALUATED; mesh/Tie/material review remains independent'
    r['stress_rule']='RAW INTEGRATION_POINT S.mises; all stored section points; no nodal averaging'
    r['source_units']='m-N-Pa (project convention; ODB has no intrinsic units)'
    r['display_rule']='S tensor scaled Pa to MPa; Visualization Mises invariant after extrapolation; element averaging OFF. Display legend is not the raw IP maximum. Shell display uses SNEG; statistics include all stored section points.'
    return r,f

def pp_render(o,f,r,c,out):
    from abaqus import session
    from abaqusConstants import TIME,MISES,INTEGRATION_POINT,NODAL,CONTOURS_ON_UNDEF,CONTOURS_ON_DEF,OFF,ON,SOLID,PNG,UNIFORM
    import visualization,displayGroupOdbToolset as dgo
    sc=session.ScratchOdb(odb=o)
    name='Step07_Display_%d'%len(sc.steps)
    st=sc.Step(name=name,description='Transient scaled display only',domain=TIME,timePeriod=1.0)
    sf=st.Frame(incrementNumber=0,frameValue=r['step_time'])
    ss=sf.FieldOutput(name='S_MPa',description='Stress MPa',field=f.fieldOutputs['S']*1e-6)
    uu=sf.FieldOutput(name='U_Magnitude_mm',description='Displacement magnitude mm',field=f.fieldOutputs['U'].getScalarField(invariant=__import__('abaqusConstants').MAGNITUDE)*1000)
    vpname='Step07 ODB Results'
    if vpname in session.viewports:vpname+=' %d'%len(session.viewports)
    vp=session.Viewport(name=vpname,origin=(0,0),width=240,height=150);vp.setValues(displayedObject=o)
    vp.odbDisplay.setFrame(step=list(o.steps.keys()).index(r['step']),frame=r['frame'])
    vp.odbDisplay.basicOptions.setValues(averageElementOutput=OFF)
    vp.odbDisplay.commonOptions.setValues(visibleEdges=__import__('abaqusConstants').ALL)
    vp.viewportAnnotationOptions.setValues(title=OFF,state=OFF,annotations=ON,compass=OFF,legend=ON,triad=ON)
    vp.viewportAnnotationOptions.setValues(legendFont='-*-helvetica-medium-r-normal-*-10-*-*-*-p-*-*-*',legendPosition=(2,85))
    session.graphicsOptions.setValues(backgroundStyle=SOLID,backgroundColor='#FFFFFF')
    session.printOptions.setValues(vpDecorations=OFF,vpBackground=ON)
    session.pngOptions.setValues(imageSize=(1600,1000))
    jobs=[('01_Global_S_Mises',None,False,r['global_stress']),('02_Global_U_Magnitude',None,True,r['global_displacement'])]
    ix=3
    for kind,label in [('supports','PurlinSupport'),('hoops','HoopGroup')]:
        for i,row in enumerate(r[kind],1):
            jobs.append(('%02d_%s_%02d_S'%(ix,label,i),row['instances'],False,row));ix+=1
    r['images']=[]
    for file,members,is_u,peak in jobs:
        chosen=members or list(o.rootAssembly.instances.keys())
        vp.odbDisplay.displayGroup.replace(leaf=dgo.LeafFromPartInstance(partInstanceName=tuple(chosen)))
        if is_u:vp.odbDisplay.setPrimaryVariable(field=uu,outputPosition=NODAL)
        else:vp.odbDisplay.setPrimaryVariable(field=ss,outputPosition=INTEGRATION_POINT,refinement=(__import__('abaqusConstants').INVARIANT,'Mises'))
        vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF if is_u else CONTOURS_ON_UNDEF,))
        vp.odbDisplay.commonOptions.setValues(deformationScaling=UNIFORM,uniformScaleFactor=1.0)
        if c.get('stress_max') and not is_u:
            vp.odbDisplay.contourOptions.setValues(minAutoCompute=OFF,maxAutoCompute=OFF,minValue=0,maxValue=c['stress_max'])
        else:vp.odbDisplay.contourOptions.setValues(minAutoCompute=ON,maxAutoCompute=ON)
        vp.view.setValues(session.views['Iso'])
        vp.view.setValues(cameraPosition=(8,-16,8),cameraTarget=(0,0,2),cameraUpVector=(0,0,1))
        vp.view.fitView();vp.view.zoom(zoomFactor=0.82)
        text=(file+' | '+r['step']+' | frame %d | t=%.6g\n'%(r['frame'],r['step_time']))
        text+=('U magnitude [mm]; deformation scale 1.0; raw nodal max %.6g mm'%peak['magnitude_mm'] if is_u else 'Mises [MPa]; averaging OFF; raw IP max %.6g MPa\n%s / element %s / IP %s'%(peak['mises_MPa'],peak['instance'],peak['element_label'],peak['integration_point']))
        annotation=o.userData.Text(name='Step07_'+file+'_%d'%len(o.userData.annotations),text=text,anchor=(2,90),offset=(0,0),font='-*-helvetica-medium-r-normal-*-10-*-*-*-p-*-*-*',color='#000000')
        vp.plotAnnotation(annotation=annotation)
        path=os.path.join(out,file)
        session.printToFile(fileName=pp_api(path),format=PNG,canvasObjects=(vp,))
        displayed=vp.getPrimVarMinMaxLoc()
        active=vp.getActiveElementLabels(printResults=False)
        visible=[k for k,v in active.items() if len(v)]
        if members and set(visible)!=set(members):raise ValueError('DISPLAY_GROUP_MISMATCH: '+str(visible))
        del o.userData.annotations[annotation.name]
        r['images'].append(dict(path=path+'.png',instances=chosen,visible_instances=visible,display_extrema=displayed,unit='mm' if is_u else 'MPa',deformation_scale=1.0 if is_u else 0,averaging='OFF',numeric_peak=peak.get('mises_MPa',peak.get('magnitude_mm'))))

def pp_excel_cn(value):
    translations={
        'SUCCESS':u'提取成功','FAILED':u'失败','REVIEW_REQUIRED':u'需要人工审核',
        'EXTRACTED':u'数值已提取，后续输出待完成',
        'JOB_STATUS_COMPLETED_SUCCESSFULLY':u'求解正常完成',
        'PENDING_MATERIAL_STRENGTH':u'待确认材料强度，暂不计算安全系数',
        'USER_SELECTED_ODB_CASE_NOT_INFERRED':u'用户选择的 ODB；工况尚未注明，请人工核对',
        'POS original design, end support (matching INP)':u'原设计正压工况，端部榀（已核对对应 INP）',
        'NOT_AVAILABLE_IN_ODB_NO_COORD_FIELD':u'ODB 未提供积分点坐标，不以单元中心代替',
        'NOT_EVALUATED; mesh/Tie/material review remains independent':u'未作工程验收；网格、Tie 和材料仍需独立审核',
        'MATCHING_DAT_NOT_AVAILABLE':u'未找到同名 DAT，求解警告资料不完整',
        'None':u'不适用',
    }
    if value is None:return u'未提供'
    if isinstance(value,bool):return u'是' if value else u'否'
    if isinstance(value,(list,dict)):return json.dumps(value,ensure_ascii=False)
    return translations.get(value,value)

def pp_excel_sheets(r,c):
    overall=[[u'指标',u'结果'],[u'工程编号',c['project_id']],[u'计算任务编号',c['job_id']],
             [u'工况说明',pp_excel_cn(c['case_label'])],[u'ODB 文件路径',c['odb']],[u'分析步',r['step']],
             [u'帧编号（从 0 开始）',r['frame']],[u'分析步时间',r['step_time']],
             [u'整体最大 Mises 应力（MPa，原始积分点）',r['global_stress']['mises_MPa']],
             [u'整体最大位移（mm）',r['global_displacement']['magnitude_mm']],
             [u'求解完成状态',pp_excel_cn(r['calculation_status'])],[u'结果提取状态',pp_excel_cn(r['status'])],
             [u'最大应力对应檩托',r['controlling_support']],[u'最大应力对应抱箍组',r['controlling_hoop']],
             [u'工程审核状态',u'提取成功不等于工程验收通过；请独立审核网格、Tie 和材料。']]
    sheets=[(u'整体结果',overall)]
    for kind,title in [('supports',u'檩托结果'),('hoops',u'抱箍组结果')]:
        rows=[[u'构件／组合编号',u'包含实例',u'最大 Mises 应力（MPa，原始积分点）',u'峰值所在实例',u'单元编号',u'积分点编号',u'截面点',u'单元类型',u'安全系数／材料状态']]
        for p in r[kind]:rows.append([p['group'],', '.join(p['instances']),p['mises_MPa'],p['instance'],p['element_label'],p['integration_point'],pp_excel_cn(p['section_point']),p['element_type'],pp_excel_cn(p['safety_factor'])])
        sheets.append((title,rows))
    labels={'status':u'结果提取状态','calculation_status':u'求解完成状态','step':u'分析步','frame':u'帧编号（从 0 开始）','step_time':u'分析步时间','timestamp':u'提取时间',
            'source_sha256_before':u'提取前 ODB SHA256','source_sha256_after':u'提取后 ODB SHA256','source_unchanged':u'源 ODB 是否保持不变','engineering_acceptance':u'工程审核状态','solver_warnings':u'ODB 诊断记录的求解警告数','solver_errors':u'ODB 诊断记录的求解错误数',
            'project_id':u'工程编号','model_name':u'目标模型名称','job_id':u'计算任务编号','case_label':u'工况说明','odb':u'ODB 原始路径','summary':u'装配摘要路径','version':u'后处理程序版本','strength_status':u'材料强度确认状态'}
    info=[[u'项目',u'内容／说明']]
    for k in ('status','calculation_status','step','frame','step_time','timestamp','source_sha256_before','source_sha256_after','source_unchanged','engineering_acceptance','solver_warnings','solver_errors'):info.append([labels[k],pp_excel_cn(r.get(k,''))])
    info.extend([[u'最大应力统计口径',u'所有已保存截面点的未平均积分点 Mises 最大值，不使用节点平均峰值。'],
                 [u'云图显示口径',u'应力张量由 Pa 换算为 MPa 后由 Abaqus 外推绘图；关闭节点平均；壳体显示 SNEG。云图峰值与原始积分点峰值分开记录。'],
                 [u'单位换算',u'模型约定 m–N–Pa；应力除以 10⁶ 得 MPa，位移乘以 1000 得 mm。ODB 本身不内置单位。']])
    for k in ('project_id','model_name','job_id','case_label','odb','summary','version','strength_status'):info.append([labels[k],pp_excel_cn(c.get(k,''))])
    peak_labels={'mises_MPa':u'最大 Mises 应力（MPa）','instance':u'峰值所在实例','element_label':u'单元编号','integration_point':u'积分点编号','section_point':u'截面点','element_type':u'单元类型','integration_point_coordinates':u'积分点坐标','coordinate_status':u'坐标说明','sample_count':u'参与统计的积分点结果数','safety_factor':u'安全系数／材料状态','magnitude_mm':u'最大位移模量（mm）','node_label':u'节点编号','components_mm':u'位移分量 U1、U2、U3（mm）'}
    for kind,title in [('global_stress',u'整体应力'),('global_displacement',u'整体位移')]:
        for k,v in sorted(r[kind].items()):info.append([title+u'：'+peak_labels.get(k,k),pp_excel_cn(v)])
    warning_names={'WarnNodeMissMasterIntersect':u'Tie 从面节点未找到主面投影','WarnNodeAdjust':u'Tie 初始位置调整节点','WarnElemDistorted':u'畸变单元警告','STEP07_QA_ANALYSIS_WARN':u'网格阶段质量警告单元'}
    for i,w in enumerate(r['warnings'],1):
        info.append([u'网格／Tie 警告 %d'%i,u'%s；所属实例／装配：%s；集合：%s；数量：%s'%(warning_names.get(w['set'],u'求解器警告集合'),w['owner'],w['set'],w.get('count',u'未统计'))])
    for i,w in enumerate(r['dat_warning_excerpts'],1):info.append([u'DAT 原始警告 %d（保留英文供追溯）'%i,pp_excel_cn(w)])
    for item in r.get('images',[]):
        d=item.get('display_extrema') or {}
        info.append([u'云图：'+os.path.basename(item['path']),u'显示峰值：%s；原始积分点／节点峰值：%s；单位：%s。两种口径不可混用。'%(d.get('maxValue',u'未提供'),item['numeric_peak'],item['unit'])])
    sheets.append((u'计算说明与警告',info))
    base=r.get('base_reaction',{})
    rows=[[u'基础 RP 集合',u'所属实例／装配',u'节点编号',u'RF1（N，全局 X）',u'RF2（N，全局 Y）',u'RF3（N，全局 Z）',u'反力合力（N）']]
    for row in base.get('rows',[]):rows.append([row['set'],row['instance'],row['node_label']]+row['components_N']+[row['magnitude_N']])
    if base.get('status')=='SUCCESS':rows.append([u'基底合计（矢量求和）','','']+base['total_components_N']+[base['total_magnitude_N']])
    rows.append([u'提取状态',pp_excel_cn(base.get('status','REVIEW_REQUIRED'))])
    rows.append([u'统计范围',u'仅基础 RP；同一节点不重复计入。排除檩条端部等其他约束反力。'])
    rows.append([u'说明',u'与应力采用同一分析步及帧；RF 为支座对结构的反力。基底合力不等于全部约束反力，也不自动代表整体荷载平衡通过。'])
    if base.get('issues') or not base:
        rows.append([u'待检查原因',u'未能完整提取基底反力，不能按零处理：'+str(base.get('issues',[]))])
    sheets.append((u'基底反力',rows))
    return sheets

def pp_xlsx(path,r,c):
    # Minimal OOXML writer for Abaqus 2020 (no external Python package required).
    sheets=pp_excel_sheets(r,c)
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def val(x):
        try:return unicode(x)
        except NameError:return str(x)
    def col(n):
        s=''
        while n:n,a=divmod(n-1,26);s=chr(65+a)+s
        return s
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'%i for i in range(1,len(sheets)+1))+'</Types>')
        relns='http://schemas.openxmlformats.org/package/2006/relationships'
        z.writestr('_rels/.rels','<Relationships xmlns="'+relns+'"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',('<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'%(name,i,i) for i,(name,rows) in enumerate(sheets,1))+'</sheets></workbook>').encode('utf-8'))
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="'+relns+'">'+''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'%(i,i) for i in range(1,len(sheets)+1))+'<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml','<styleSheet xmlns="'+ns+'"><numFmts count="1"><numFmt numFmtId="164" formatCode="0.000"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="4"><xf fontId="0" fillId="0" borderId="0" numFmtId="0" xfId="0"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" numFmtId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf><xf fontId="0" fillId="0" borderId="0" numFmtId="164" xfId="0" applyNumberFormat="1"/><xf fontId="0" fillId="0" borderId="0" numFmtId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i,(name,rows) in enumerate(sheets,1):
            xml='<worksheet xmlns="'+ns+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="32" customWidth="1"/><col min="2" max="2" width="65" customWidth="1"/><col min="3" max="9" width="24" customWidth="1"/></cols><sheetData>'
            for ri,row in enumerate(rows,1):
                xml+='<row r="%d" ht="%d" customHeight="1">'%(ri,44 if ri==1 else 68 if name==u'计算说明与警告' else 42)
                for ci,x in enumerate(row,1):
                    ref=col(ci)+str(ri)
                    if isinstance(x,(int,float)) and not isinstance(x,bool):xml+='<c r="%s" s="%s"><v>%s</v></c>'%(ref,'2' if isinstance(x,float) else '3',x)
                    else:xml+='<c r="%s" s="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'%(ref,'1' if ri==1 else '0',escape(val(x)))
                xml+='</row>'
            xml+='</sheetData></worksheet>';z.writestr('xl/worksheets/sheet%d.xml'%i,xml.encode('utf-8'))

def pp_run(c):
    from abaqus import session
    import visualization
    out=pp_new_dir(c['output_root'],c['job_id']);r={'status':'FAILED','output':out,'plan':c}
    logfile=open(os.path.join(out,'postprocess.log'),'w');o=None;owned=False;digest=None
    def log(s):
        print(s)
        try:
            if isinstance(s,unicode):s=s.encode('utf-8')
        except NameError:pass
        logfile.write(s+'\n');logfile.flush()
    try:
        log('Stage07 READ_ONLY ODB: '+c['odb'])
        if pp_hash(c['summary'])!=c['summary_sha256']:raise ValueError('ASSEMBLY_SUMMARY_CHANGED_REGENERATE_SCRIPT')
        digest=pp_hash(c['odb']);log('SOURCE_SHA256 '+digest)
        # Reuse only a read-only ODB already opened by the user; never close it.
        for existing in session.odbs.values():
            if os.path.normcase(os.path.abspath(existing.path))==os.path.normcase(os.path.abspath(c['odb'])):o=existing;break
        if o is None:o=session.openOdb(name=pp_api(c['odb']),readOnly=True);owned=True
        if not o.isReadOnly:raise ValueError('ODB_ALREADY_OPEN_WRITABLE_CLOSE_IT_MANUALLY')
        result,f=pp_extract(o,c);r.update(result);r['output']=out;r['source_sha256_before']=digest;r['timestamp']=datetime.datetime.now().isoformat()
        log('Numerical extraction PASS: %d supports, %d hoop groups'%(len(r['supports']),len(r['hoops'])))
        pp_json(os.path.join(out,'numerical_results.json'),r)
        pp_render(o,f,r,c,out);log('Visualization PNGs: '+str(len(r['images'])))
        r['status']='SUCCESS'
    except Exception:
        r['status']='FAILED';r['error']=traceback.format_exc();log(r['error'])
    finally:
        if owned and o is not None:
            try:o.close()
            except Exception:r['status']='FAILED';r['close_error']=traceback.format_exc()
        if digest is not None:
            try:
                r['source_sha256_after']=pp_hash(c['odb']);r['source_unchanged']=r['source_sha256_after']==digest
                if not r['source_unchanged']:r['status']='FAILED';r['source_error']='SOURCE_ODB_CHANGED'
            except Exception:r['status']='FAILED';r['source_error']=traceback.format_exc()
        try:
            if 'global_stress' in r:
                x=os.path.join(out,c['project_id']+'_'+c['job_id']+'_ODB_Results.xlsx');pp_xlsx(x,r,c);r['excel']=x
        except Exception:r['status']='FAILED';r['excel_error']=traceback.format_exc()
        pp_json(os.path.join(out,'results.json'),r);log('RESULT '+r['status']+' '+out);logfile.close()
    if r['status']!='SUCCESS':raise RuntimeError('ODB_POSTPROCESS_FAILED: '+out)
    return r
