"""Project-level hole workbook schema and application template generator.

Uses the application's existing openpyxl dependency, including in the frozen EXE.
No dimensions are inferred from drawings or another project's workbook.
"""
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .analysis_discovery import safe_project_id, linked
from .hole_inputs import CHINESE_HEADERS, FULL_FIELDS, normalize_records, _enabled, VALUES
from .hole_plan import _instances, _role
from .hoop_hole_plan import unique_hoop_parts, build_hoop_hole_plan

SUFFIX = '_螺栓孔定位表.xlsx'
SCHEMA = 'CADtoCAE-Step06-Project-Hole-Table-v1'
META_SHEET = '_STEP06_META'
META_SCHEMA = 'step06-project-hole-table-v1'
SUPPORT_SHEET, HOOP_SHEET = '檩托孔位', '抱箍孔位'
SUPPORT_HEADERS = CHINESE_HEADERS[2:]
HOOP_HEADERS = ('构件','适用Part','孔位编号','端部基准','距端部 (mm)',
                '距宽边 (mm)','孔型','孔径 (mm)','启用','备注')
HOOP_FIELDS = ('component_role','part_name','hole_id','end_reference','distance_from_end_mm',
               'distance_from_side_mm','hole_type','diameter_mm','enabled','note')


class NeedsInput(ValueError):
    pass


def project_id_from_filename(path):
    name = Path(path).name
    if not name.endswith(SUFFIX):
        raise ValueError('Expected <project_id>'+SUFFIX)
    project = name[:-len(SUFFIX)]
    safe_project_id(project)
    return project


def _metadata_warnings(workbook, project, warnings):
    # Office core/custom properties and defined names are not identity sources.
    rows = list(workbook[META_SHEET].values) if META_SHEET in workbook.sheetnames else []
    ids = [row[1] for row in rows if len(row)>1 and row[0]=='project_id' and row[1] not in (None,'')]
    if any(value != project for value in ids):
        raise ValueError('Workbook metadata conflicts with filename identity')
    if not ids:
        warnings.append('Workbook metadata missing; filename identity used.')
    versions = [row[1] for row in rows if len(row)>1 and row[0]=='schema_version']
    if ids and versions != [META_SCHEMA]:
        warnings.append('Workbook metadata schema version missing or unknown; visible sheet/header schema used.')


def workbook_path(folder, project):
    safe_project_id(project)
    return Path(folder)/(project+SUFFIX)


def template_catalog(summary, components):
    supports = [m for m in _instances(summary) if _role(m)=='PURLIN_SUPPORT']
    parts = {m['part_name'] for m in supports}
    if len(parts)!=1 or not any(m.get('connection_group')=='P01' for m in supports):
        raise ValueError('Current support sheet requires one standard PURLIN_SUPPORT Part with P01 mapping')
    return unique_hoop_parts(summary,components)


def _style(sheet, headers, rows, editable, widths, help_text, choices):
    sheet.append([sheet.title+'（mm）'])
    sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers))
    sheet.cell(1,1).font = Font(name='Microsoft YaHei',size=14,bold=True,color='17365D')
    sheet.row_dimensions[1].height=30
    sheet.append([help_text])
    sheet.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers))
    sheet.cell(2,1).alignment=Alignment(wrap_text=True,vertical='center')
    sheet.row_dimensions[2].height=42
    sheet.append(headers)
    sheet.row_dimensions[3].height=44
    for row in rows:
        sheet.append(row)
    for cell in sheet[3]:
        cell.fill=PatternFill('solid',fgColor='234E70')
        cell.font=Font(name='Microsoft YaHei',size=10,bold=True,color='FFFFFF')
        cell.alignment=Alignment(wrap_text=True,vertical='center',horizontal='center')
    for i,width in enumerate(widths,1):
        sheet.column_dimensions[get_column_letter(i)].width=width
    for row in sheet.iter_rows(min_row=4,max_row=3+len(rows)):
        sheet.row_dimensions[row[0].row].height=32
        for cell in row:
            edit = cell.column in editable
            cell.protection=Protection(locked=not edit)
            cell.fill=PatternFill('solid',fgColor='FFF2CC' if edit else 'EAF0F5')
            cell.font=Font(name='Microsoft YaHei',size=10,color='1F3864' if edit else '333333')
            cell.alignment=Alignment(vertical='center',wrap_text=True)
            if cell.column in editable and headers[cell.column-1].endswith('(mm)'):
                cell.number_format='0.###'
    for col,values in choices.items():
        if not rows:continue
        validation=DataValidation(type='list',formula1='"'+','.join(values)+'"',allow_blank=False)
        validation.errorTitle='请选择列表中的值';validation.error='请使用下拉列表。'
        validation.showErrorMessage=True;validation.errorStyle='stop'
        sheet.add_data_validation(validation)
        validation.add('%s4:%s%d'%(get_column_letter(col),get_column_letter(col),3+len(rows)))
    sheet.freeze_panes='C4';sheet.sheet_view.showGridLines=False
    sheet.protection.sheet=True
    sheet.protection.selectLockedCells=False;sheet.protection.selectUnlockedCells=False
    sheet.print_title_rows='1:3';sheet.sheet_properties.pageSetUpPr.fitToPage=True
    sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    sheet.print_options.horizontalCentered=True
    sheet.print_area='A1:%s%d'%(get_column_letter(len(headers)),max(4,3+len(rows)))


def create_hole_workbook(folder, project, summary, components):
    path = workbook_path(folder,project)
    if path.exists() or path.is_symlink():
        return dict(path=str(path),status='PRESERVED',message='Existing hole table preserved.')
    if summary.get('project_id') != project:
        raise ValueError('Summary/project filename mismatch')
    catalog = template_catalog(summary,components)
    wb=Workbook();wb.remove(wb.active)
    wb.properties.subject=SCHEMA;wb.properties.identifier=project
    support=[['檩托','PS_TO_PURLIN','局部檩条','长肢',None,None,'起始端','长圆孔',None,None,'沿长肢方向','是',''],
             ['檩托','PS_TO_BEAM','斜梁','短肢',None,None,'起始端','长圆孔',None,None,'沿檩托长度方向','是','']]
    _style(wb.create_sheet(SUPPORT_SHEET),SUPPORT_HEADERS,support,{5,6,7,8,9,10,11,12,13},
           [12,23,14,14,24,17,13,13,19,18,24,10,34],
           '黄色单元格可填写；尺寸均为 mm。根部以角钢外侧两平面理论交线为零点；标准孔自动应用到同一 Part 的全部对应实例。',
           {7:['起始端','末端'],8:['长圆孔','圆孔'],11:['沿肢方向','沿檩托长度方向'],12:['是','否']})
    hoop=[]
    for part in sorted(catalog):
        for hole,end in [('HOOP_LEFT','左端'),('HOOP_RIGHT','右端')]:
            hoop.append(['抱箍',part,hole,end,None,None,'圆孔',None,'是',''])
    _style(wb.create_sheet(HOOP_SHEET),HOOP_HEADERS,hoop,{5,6,8,9,10},
           [12,48,22,13,18,18,12,16,10,34],
           '黄色单元格可填写；适用Part只读。左/右端按 Part 局部 X 最小/最大端；距宽边从局部 Z=0 量取。圆孔贯穿平直耳板厚度；不得进入圆弧或过渡圆角。',
           {9:['是','否']})
    meta=wb.create_sheet(META_SHEET)
    meta.append(['schema_version',META_SCHEMA])
    meta.append(['project_id',project])
    meta.sheet_state='hidden'
    try:
        stream=BytesIO();wb.save(stream)
        # Exclusive create also protects an existing file appearing after the first check.
        try:
            with path.open('xb') as output:
                output.write(stream.getvalue())
        except FileExistsError:
            return dict(path=str(path),status='PRESERVED',message='Existing hole table preserved.')
    finally:
        wb.close()
    return dict(path=str(path),status='CREATED',message='Hole table created; fill highlighted dimensions.')


def _read_sheet(sheet, headers, fields):
    # Two instruction rows, then an exact project schema (column order is stable).
    actual=tuple(sheet.cell(3,i).value for i in range(1,sheet.max_column+1))
    if actual != tuple(headers):
        raise ValueError('Invalid project workbook headers: '+sheet.title)
    rows=[]
    for number,values in enumerate(sheet.iter_rows(min_row=4,values_only=True),4):
        if not any(v is not None for v in values):continue
        if any(isinstance(v,str) and v.startswith('=') for v in values):
            raise ValueError('Formulas are unsupported: %s:%d'%(sheet.title,number))
        rows.append((number,dict(zip(fields,values))))
    return rows


def _missing(row, keys, location):
    missing=[k for k in keys if row.get(k) in (None,'')]
    if missing:raise NeedsInput(location+': fill '+', '.join(missing))


def read_project_hole_workbook(path, project, summary, components, warnings=None):
    path=Path(path)
    if project_id_from_filename(path) != project or linked(path):
        raise ValueError('Project hole workbook filename mismatch or linked workbook')
    if warnings is None:
        warnings=[]
    catalog=template_catalog(summary,components)
    with path.open('rb') as stream:
        wb=load_workbook(stream,read_only=True,data_only=False)
        try:
            if set(wb.sheetnames) not in ({SUPPORT_SHEET,HOOP_SHEET}, {SUPPORT_SHEET,HOOP_SHEET,META_SHEET}):
                raise ValueError('Invalid project workbook schema: expected 檩托孔位 and 抱箍孔位')
            _metadata_warnings(wb,project,warnings)
            support=_read_sheet(wb[SUPPORT_SHEET],SUPPORT_HEADERS,FULL_FIELDS[2:])
            hoops=_read_sheet(wb[HOOP_SHEET],HOOP_HEADERS,HOOP_FIELDS)
        finally:wb.close()
    records=[]
    for number,row in support:
        _missing(row,['distance_from_angle_corner_mm','distance_from_end_mm','hole_diameter_mm'],SUPPORT_SHEET+':'+str(number))
        if row['hole_type'] in ('长圆孔','SLOT'):
            _missing(row,['slot_total_length_mm','slot_major_axis'],SUPPORT_SHEET+':'+str(number))
        row.update(project_id=project,connection_group='P01')
        records.append(dict(values=row,source_file=str(path.resolve()),source_sheet=SUPPORT_SHEET,source_row=number))
    if len(records)!=2:raise ValueError('Support sheet requires exactly two standard hole rows')
    support_rows=normalize_records(records)
    hoop_rows=[]
    for number,row in hoops:
        row={k: v.strip() if isinstance(v,str) else v for k,v in row.items()}
        if row['component_role'] not in ('抱箍','HOOP'):raise ValueError('Expected HOOP component')
        row['enabled']=_enabled(VALUES.get(row['enabled'],row['enabled']))
        row['end_reference']={'左端':'LEFT','右端':'RIGHT'}.get(row['end_reference'],row['end_reference'])
        row['hole_type']=VALUES.get(row['hole_type'],row['hole_type'])
        if row['enabled']:
            _missing(row,['distance_from_end_mm','distance_from_side_mm','diameter_mm'],HOOP_SHEET+':'+str(number))
        hoop_rows.append(row)
    return support_rows,build_hoop_hole_plan(catalog,hoop_rows)
