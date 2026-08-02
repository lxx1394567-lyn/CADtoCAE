# CADtoCAE 项目管理标准

本项目后续统一采用：

> 源代码重点管理，生成文件原则上不管理，正式发布文件单独归档。

## 目录职责

- `src/`：核心 Python 库代码。
- `scripts/`：Step01、Step02、Step04 命令行、GUI 和打包入口。
- `config/`：支架类型、命名规则、材料和截面标准。
- `templates/`：用户需要填写或复制使用的固定模板。
- `examples/`：轻量演示数据。
- `docs/`：说明书、流程图、项目管理规则。
- `tests/`：自动化测试。
- `real_tests/`：少量人工筛选后的回归样例。
- `build/`、`dist/`、`outputs/`：本地生成目录，不进入 git。

## Git 管理范围

纳入 git：

- 源代码、脚本入口和测试代码
- 配置、模板、轻量示例和说明文档
- `CHANGELOG.md`
- 必要的回归测试样例

不纳入 git：

- 用户项目输出文件，例如 `<project_prefix>_components.xlsx`、`<project_prefix>_create_parts_in_cae.py`、`<project_prefix>_assembly_frame.py`
- 调试报告、过程文件、OCR 中间结果
- Abaqus 生成的 `.cae`、`.odb`、`.jnl`、`.rec` 等文件
- PyInstaller 的 `build/`、`dist/`、`*.spec`
- 正式发布 zip

如果需要保留一套标准示例，优先放到 `examples/` 或经过筛选的 `real_tests/`，必要时用 `git add -f` 明确加入。

## 稳定基线

当前稳定基线保护已经跑通的单桩单立柱半自动化建模流程：

1. Step01 读取材料表截图并生成 `<project_prefix>_components.xlsx`。
2. Step02 生成 `<project_prefix>_create_parts_in_cae.py`，组件数据嵌入脚本。
3. 用户填写 `<project_prefix>_coordinate_formula_simple_fixed.xlsx`。
4. Step04 生成 `<project_prefix>_assembly_frame.py`，装配数据嵌入脚本。

当前 tag：`v0.1-sp-sc-semi-auto-assembly`。

## 分支策略

- `main`：稳定可用版本。
- `feature/step02-all-components`：扩展 Step02，实现更多构件自动 Part 建模。
- `feature/step04-sp-dc-dp-assembly`：扩展坐标模板和 Step04，支持单桩双立柱、双桩双立柱 assembly。
- `feature/step05-analysis-submit`：后续实现 interaction、step、load、boundary、job submit。

提交说明建议使用：

- `新增：...`
- `修复：...`
- `优化：...`
- `文档：...`
- `发布：...`

避免使用 `最终版`、`最终版2`、`测试`、`111` 这类无法追踪含义的提交说明。

## 发布包

exe 不直接放进 git。每个稳定版本单独打 zip 发布包，建议放在本地：

```text
release_packages/CADtoCAE_vX.Y.Z_YYYYMMDD.zip
```

发布包应包含：

- `dist/` 下的 exe 文件夹
- `docs/` 使用说明
- `config/standards.json`
- `templates/` 固定模板
- 必要演示数据

## 每次提交前检查

```powershell
$env:PYTHONPATH='src'
.\.venv_step01_build\Scripts\python.exe -m unittest discover -s tests -v
```

涉及 Step02 或 Step04 时，还应重跑 `real_tests` 中的 ANG18/ANG33 样例，并确认：

- 不生成外部 `components.json` 或 `assembly_inputs.json`
- 调试报告进入 `过程文件\调试文件`
- Abaqus 脚本只操作同名 `<project_prefix>` Model

## 远程仓库

如果后续上传 GitHub 或 Gitee，建议使用私有仓库。涉及单位图纸、科研项目资料、大型 PDF、CAE 数据库和计算结果时，不要放入公开仓库。
