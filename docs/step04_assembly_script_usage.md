# CADtoCAE Step04 Assembly Script 使用说明

## 输入文件

把同一个项目的两个文件放在同一个文件夹中：

- `<project_prefix>_coordinate_formula_simple_fixed.xlsx`
- `<project_prefix>_create_parts_in_cae.py`

其中 `<project_prefix>` 必须一致，例如：

- `SP_SC_ANG18_coordinate_formula_simple_fixed.xlsx`
- `SP_SC_ANG18_create_parts_in_cae.py`

坐标表由用户自行填写；`create_parts_in_cae.py` 由 Step02 生成。旧版本的 `<project_prefix>_components.json` 仍可兼容读取，但新流程不再需要这个文件。

## 运行 exe

双击 `CADtoCAE_Step04_AssemblyScript.exe`，选择坐标表所在文件夹，然后点击“生成 Assembly 脚本”。

程序会自动扫描该文件夹中的 `*_coordinate_formula_simple_fixed.xlsx`，并按文件名前缀寻找对应的 `<project_prefix>_create_parts_in_cae.py`。

## 输出文件

Assembly 脚本会直接生成在所选文件夹根目录内：

- `<project_prefix>_assembly_frame.py`

开发者调试报告会保存到固定子目录：

- `过程文件\调试文件\<project_prefix>_step04_assembly_script_report.json`

## 在 Abaqus/CAE 中使用

1. 打开需要建模的 `.cae` 文件。
2. 先运行 Step02 生成的 `<project_prefix>_create_parts_in_cae.py`，创建同名 Model 和 Part。
3. 再运行 Step04 生成的 Assembly 脚本。

Step04 脚本只会操作名称等于 `<project_prefix>` 的 Abaqus Model。若当前 CAE 文件中没有该 Model，脚本会停止并提示先运行 Step02。
Step04 的装配数据已经嵌入到 `<project_prefix>_assembly_frame.py` 中，运行 Abaqus 时不需要额外携带 json 文件。

## 注意事项

- 不要手动把 Assembly 脚本中的 Model 名改成 `Model-1` 或其他项目名。
- Step04 不会新建或修改其他 Model。
- Step04 不再生成额外参考点 RP；装配定位直接依据坐标表中的控制点和已有 Part 几何完成。
- 斜梁 `INCLINED_BEAM` 会在完成轴线定位后，额外绕自身中心轴旋转 180°。
