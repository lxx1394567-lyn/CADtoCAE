# CADtoCAE 项目管理说明

## 稳定基线

当前稳定基线用于保护已经跑通的单桩单立柱半自动化建模流程：

1. Step01 读取材料表截图并生成 `<project_prefix>_components.xlsx`。
2. Step02 生成 `<project_prefix>_create_parts_in_cae.py`，组件数据嵌入脚本。
3. 用户填写 `<project_prefix>_coordinate_formula_simple_fixed.xlsx`。
4. Step04 生成 `<project_prefix>_assembly_frame.py`，装配数据嵌入脚本。

首个稳定 tag 建议命名为 `v0.1-sp-sc-semi-auto-assembly`。

## Git 管理范围

纳入 git 的内容：

- `src/`、`scripts/`、`config/`、`docs/`、`tests/`
- `examples/` 中的轻量样例
- 必要的 `real_tests/` 回归样例
- `README.md`、`pyproject.toml`、依赖清单

不纳入 git 的内容：

- `.venv_step01_build/`
- `build/`、`dist/`
- `outputs/`
- Abaqus 生成的 `.cae`、`.jnl`、`.rec`
- 大型图纸、截图、临时调试报告和发布 zip

## 分支策略

- `main`：稳定可用版本。
- `feature/step02-all-components`：扩展 Step02，实现更多构件自动 Part 建模。
- `feature/step04-sp-dc-dp-assembly`：扩展坐标模板和 Step04，支持单桩双立柱、双桩双立柱 assembly。
- `feature/step05-analysis-submit`：后续实现 interaction、step、load、boundary、job submit。

## 发布包

exe 不直接放进 git。每个稳定版本单独打 zip 发布包，建议放在本地：

```text
release_packages/CADtoCAE_v0.1_YYYYMMDD.zip
```

发布包应包含：

- `dist/` 下的 exe 文件夹
- `docs/` 使用说明
- `config/standards.json`
- 必要模板和演示数据

## 每次提交前检查

```powershell
$env:PYTHONPATH='src'
.\.venv_step01_build\Scripts\python.exe -m unittest discover -s tests -v
```

涉及 Step02 或 Step04 时，还应重跑 `real_tests` 中的 ANG18/ANG33 样例，并确认：

- 不生成外部 `components.json` 或 `assembly_inputs.json`
- 调试报告进入 `过程文件\调试文件`
- Abaqus 脚本只操作同名 `<project_prefix>` Model
