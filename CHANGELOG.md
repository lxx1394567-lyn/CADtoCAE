# 更新记录

## v0.1.1 - 2026-08-02

### 优化
- Step01 生成的 `建模构件表` 关键列改为公式联动 `原始材料表`，减少用户重复修改。
- `abaqus_part_name`、长度换算、材料牌号、建模方式和单元类型按项目规则自动更新。
- Step02 增加公式工作簿兜底读取，未打开 Excel 重算时也能按 `原始材料表` 当前内容生成 Part 脚本。

### 文档
- 更新 Step01 使用说明，明确优先校核和修改 `原始材料表`。

## v0.1.0 - 2026-08-02

### 新增
- 建立单桩单立柱光伏支架半自动化建模流程。
- Step01 支持从材料表截图生成标准化 `<project_prefix>_components.xlsx`。
- Step02 支持生成 Abaqus Part 建模脚本，组件数据嵌入 `<project_prefix>_create_parts_in_cae.py`。
- Step04 支持根据用户填写的坐标模板生成 `<project_prefix>_assembly_frame.py`。
- Step04 装配脚本只操作同名 `<project_prefix>` Model。

### 调整
- 不再要求用户携带 `<project_prefix>_components.json`。
- 不再生成外部 `assembly_inputs.json`。
- Step02 和 Step04 调试报告统一进入 `过程文件\调试文件`。
- 斜梁 `INCLINED_BEAM` 在装配时额外绕自身中心轴旋转 180°。

### 项目管理
- 建立 `main` 稳定分支。
- 建立 tag：`v0.1-sp-sc-semi-auto-assembly`。
- 增加项目管理说明，后续采用“源代码进 Git，正式发布包单独归档”的方式。
