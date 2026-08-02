# Step01 材料表识别窗口使用说明

## 打开程序

开发环境运行：

```powershell
python scripts\step01_pdf_material_gui.py
```

打包后运行：

```text
dist\CADtoCAE_Step01_MaterialTable\CADtoCAE_Step01_MaterialTable.exe
```

## 用户操作

1. 准备裁剪清晰的材料表截图，格式使用 PNG/JPG。
2. 点击“添加 PNG/JPG”选择一个或多个文件，或点击“添加文件夹”批量加入文件夹里的截图。
3. 选择 Excel 输出目录。
4. 设置默认支架类型、默认倾角和阵列布置。
5. 勾选“自动从文件名/PDF 文本识别支架类型和倾角”。
6. 点击“开始识别并生成 Excel”。

## 输出结果

每张材料表图片会生成一个单独子文件夹：

```text
<project_prefix>_<图片文件名>\
```

识别成功时输出：

```text
<project_prefix>_components.xlsx
```

识别失败或需要复核时输出：

```text
manual_material_table_template.csv
```

不会生成伪材料表行，也不会额外生成单项目 JSON 报告。识别过程和失败原因会显示在窗口日志中；用户可按 `manual_material_table_template.csv` 补录材料表，再回到后续流程。

## 建模构件表颜色说明

生成的 Excel 只保留两张 sheet：

- `原始材料表`：用于和原始截图/图纸逐项对比。
- `建模构件表`：用于检查和补充后续 Part 建模参数。

`建模构件表` 中：

- 深红色表头：Step02 会读取的关键字段。
- 浅红色单元格：需要人工补充或修正；鼠标悬停可查看批注原因。

人工补充时优先修改浅红色单元格，尤其是 `abaqus_part_name`、`规格`、`长度_mm`、`材料牌号`、`建模方式` 和 `单元类型`。`截面类型`、`截面参数`、`厚度_mm`、`厚度_m` 主要用于查看解析结果，Step02 会重新从 `规格` 列解析截面。

## OCR 说明

图片材料表默认使用内置 RapidOCR 识别。截图应完整包含材料表外框、表头和所有行；不要使用整张图纸 PDF，也不要只截一半表格。
