# 更新记录

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
