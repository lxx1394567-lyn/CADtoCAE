# CADtoCAE

Photovoltaic support drawing to Abaqus modeling inputs.

The rebuilt workflow uses one English project prefix everywhere:

```text
<support_type_code>_<angle_code>
```

Support type codes:

- `单桩单立柱` -> `SP_SC`
- `单桩双立柱` -> `SP_DC`
- `双桩` -> `DP`
- `双桩双立柱` is accepted as an alias of `双桩`

Angle code:

- `20` -> `ANG20`
- `26.5` -> `ANG26P5`

Examples: `SP_SC_ANG20`, `SP_DC_ANG20`, `DP_ANG26P5`.

## Repository Layout

```text
config/standards.json       Naming, component roles, materials, modeling policy
examples/                   Example material CSV, coordinate layout JSON, drawings
scripts/                    Four official workflow entry points
src/cadtocae/               Core Python library
tests/                      Unit and workflow tests
outputs/                    Generated run outputs
```

## Four Steps

Step01: drawing material table to Part workbook.

For end users, run the GUI or packaged exe. Step01 now uses cropped, clear material-table screenshots only, such as PNG/JPG. Do not input full PDF drawings for Step01.

```powershell
python scripts\step01_pdf_material_gui.py
```

The window lets the user select one folder or multiple material-table screenshots, choose an output folder, and set fallback support type/angle. For each input file, it creates a separate output folder and writes:

```text
<project_prefix>_components.xlsx
```

The generated workbook keeps two sheets: `原始材料表` for comparison with the source screenshot/drawing, and `建模构件表` for Part modeling inputs. Users should first correct `原始材料表`; key Step02 fields in `建模构件表`, including `abaqus_part_name`, spec, length, material grade, modeling policy, and element type, update by formulas. Manual overrides in `建模构件表` are still respected by Step02.

Batch command-line usage:

```powershell
python scripts\step01_batch_extract_materials.py `
  --input-dir "F:\material_table_images" `
  --output-dir "F:\CADtoCAE_outputs" `
  --support-type 单桩单立柱 `
  --angle 20
```

Existing CSV/OCR-checked workflow is still available:

```powershell
python scripts\step01_generate_part_excel.py `
  --manual-csv examples\single_pile_single_column_2x7_raw_materials.csv `
  --support-type 单桩单立柱 `
  --angle 20 `
  --layout 2行7列竖向
```

Output: `outputs/<prefix>_runs/<timestamp>/workbooks/<prefix>_components.xlsx`.

Step02: Part workbook to Abaqus Part script.

For end users, run the GUI or packaged exe:

```powershell
python scripts\step02_part_script_gui.py
```

Batch command-line usage:

```powershell
python scripts\step02_batch_generate_part_scripts.py `
  --input-dir "F:\CADtoCAE_step01_excels" `
  --output-dir "F:\CADtoCAE_step02_outputs" `
  --selection complete
```

```powershell
python scripts\step02_generate_part_script.py --run-dir latest
```

Outputs:

- `json/components.json`
- `abaqus_scripts/<prefix>_create_parts_in_cae.py`

The generated Abaqus model name is exactly `<prefix>`, and scripts generated in the same Step02 output folder save to the common `CADtoCAE_PARTS.cae` file.

Step03: drawing/layout to coordinate formula workbooks.

```powershell
python scripts\step03_generate_coordinate_workbooks.py `
  --coordinate-layout examples\sp_sc_ang20_coordinate_layout.json `
  --run-dir latest
```

Outputs:

- `<prefix>_coordinate_formula_full_fixed.xlsx`
- `<prefix>_coordinate_formula_simple_fixed.xlsx`

Step04: simple coordinate workbook to Abaqus Assembly scripts.

```powershell
python scripts\step04_generate_assembly_script.py --run-dir latest
```

Outputs:

- `json/assembly_inputs.json`
- `abaqus_scripts/<prefix>_step01_columns.py`
- `abaqus_scripts/<prefix>_step02_beam.py`
- `abaqus_scripts/<prefix>_step03_main_frame.py`
- `abaqus_scripts/<prefix>_create_main_frame_assembly.py`

## PDF And OCR Boundary

Step01 extracts the material table from cropped PNG/JPG screenshots. The packaged exe bundles RapidOCR when built with the provided build environment.

- If a material table is recognized, Step01 writes `<project_prefix>_components.xlsx`.
- If the material table cannot be recognized, Step01 writes `manual_material_table_template.csv` and does not create fake component rows.
- Step03 needs `--coordinate-layout` or a future structured OCR result.

Other OCR providers can still be added later behind the same structured rows without changing Step02/Step04.

## Build Step01 EXE

Install runtime and build dependencies in a Python environment:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

Build the Windows GUI executable:

```powershell
.\scripts\build_step01_exe.ps1
```

Output:

```text
dist\CADtoCAE_Step01_MaterialTable\CADtoCAE_Step01_MaterialTable.exe
```

## Abaqus Notes

Generated Abaqus scripts are self-contained where possible and use SI units:

```text
length = m
mass   = kg
force  = N
stress = Pa
```

Part names use:

```text
P_<project_prefix>_<component_code>
```

Instance names use:

```text
I_<project_prefix>_<component_code>
```

## Tests

Use the bundled or project Python environment with dependencies installed:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```
