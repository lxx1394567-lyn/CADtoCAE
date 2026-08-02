# CADtoCAE Step02 使用说明

## 功能

Step02 根据 Step01 生成的 `<project_prefix>_components.xlsx` 生成 Abaqus Part 建模脚本：

```text
<project_prefix>_create_parts_in_cae.py
```

脚本会在当前打开的 Abaqus/CAE 会话中创建或更新同名 Model，例如 `SP_SC_ANG33`，并完成 Part、材料、截面和网格创建。

脚本不会自动打开 `.cae` 文件，也不会自动保存 `.cae` 文件；打开和保存由用户在 Abaqus/CAE 中自行完成。

## 输入文件

选择 Step01 输出的 Excel 文件，通常命名为：

```text
<project_prefix>_components.xlsx
```

例如：

```text
SP_SC_ANG33_components.xlsx
```

Step02 主要读取 sheet `建模构件表`。Step01 已用颜色标注关键列，尤其是：

- `构件名称`
- `abaqus_part_name`
- `规格`
- `长度_mm`
- `数量`
- `材料牌号`
- `建模方式`
- `单元类型`
- `截面类型`
- `截面参数`
- `厚度_mm`

## 输出文件

Step02 会把主要产物直接保存到用户选择的输出目录根目录下：

```text
<project_prefix>_create_parts_in_cae.py
```

例如：

```text
SP_SC_ANG33_create_parts_in_cae.py
```

`components` 数据已经嵌入到 `<project_prefix>_create_parts_in_cae.py` 中，不再单独生成 `<project_prefix>_components.json`。

开发者调试报告会保存到输出目录下的固定子目录：

```text
过程文件\调试文件\<project_prefix>_step02_part_script_report.json
```

例如：

```text
过程文件\调试文件\SP_SC_ANG33_step02_part_script_report.json
```

## 在 Abaqus 中运行

1. 打开 Abaqus/CAE。
2. 新建一个 CAE，或打开已有 `.cae` 文件。
3. 点击 `File -> Run Script`。
4. 选择 Step02 生成的脚本，例如 `SP_SC_ANG33_create_parts_in_cae.py`。
5. 脚本会在当前 CAE 会话中新建或更新 `SP_SC_ANG33` Model，并生成对应 Parts。
6. 用户在 Abaqus/CAE 中自行保存 `.cae` 文件。

## 多项目

多个项目可以依次运行各自的 Step02 脚本，并保存在同一个 `.cae` 文件中。每个项目会创建或更新独立 Model，例如：

```text
SP_SC_ANG18
SP_SC_ANG33
```

如果同名 Model 已存在，脚本会进入该 Model，并覆盖同名 Part，便于修改 Excel 后重复生成。
