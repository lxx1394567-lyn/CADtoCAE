# Step02 Part 自动建模脚本生成使用说明

## 打开程序

开发环境运行：

```powershell
python scripts\step02_part_script_gui.py
```

打包后运行：

```text
dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe
```

## 用户操作

1. 准备 Step01 生成并检查过的 `<project_prefix>_components.xlsx`。
2. 点击“添加 Excel”选择一个或多个文件，或点击“添加文件夹”批量加入文件夹里的 Excel。
3. 选择输出目录。
4. 导出模式保持“完整构件（推荐）”。
5. 点击“生成 Part 建模脚本”。

## 输出结果

成功时，每个项目会生成：

```text
<project_prefix>_create_parts_in_cae.py
```

`<project_prefix>_create_parts_in_cae.py` 可在 Abaqus/CAE 中运行，用于自动创建 Part、材料、截面和网格。构件数据已经嵌入该 py 文件中，不再需要单独携带 `components.json`。

开发者调试报告保存在：

```text
过程文件\调试文件\<project_prefix>_step02_part_script_report.json
```

脚本中的 Abaqus Model 名直接使用 `<project_prefix>`，例如 `SP_SC_ANG18`。

## 导出模式

完整构件（推荐）：`建模构件表` 中已按 Step01 标红列补全，且规格、长度、数量、材料牌号、建模方式、单元类型和 `abaqus_part_name` 满足自动建模要求即可导出。
