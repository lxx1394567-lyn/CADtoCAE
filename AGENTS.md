# CADtoCAE Codex 操作规则

## 基本原则

1. 修改代码前先执行 `git status --short --branch`。
2. `main` 只保留稳定可用版本。
3. 新功能必须在 `feature/*` 分支开发。
4. Bug 修复必须在 `fix/*` 分支开发。
5. 文档类修改可以使用 `docs/*` 分支。
6. 不自动 push，除非用户明确要求。

## 禁止的高风险操作

未经用户明确授权，不得执行：

- `git reset --hard`
- `git clean -fd`
- `git push --force`
- `git push --force-with-lease`
- `git branch -D`
- 批量删除或移动未确认范围的文件

回退版本前必须先创建 `backup/*` 备份分支。

## Git 提交规则

提交前必须检查：

```powershell
git status --short
git diff --stat
```

提交说明使用清晰前缀：

- `新增：...`
- `修复：...`
- `优化：...`
- `文档：...`
- `发布：...`

避免使用：

- `修改一下`
- `更新`
- `测试`
- `最终版`
- `最终版2`

## 不提交的文件

不得把以下内容提交到 git：

- `.venv_step01_build/`
- `build/`
- `dist/`
- `outputs/`
- `release_packages/`
- `*.spec`
- `*.zip`
- `*.cae`
- `*.odb`
- `*.jnl`
- `*.rec`
- `*.lck`
- 用户项目生成文件
- 调试报告和过程文件
- 未脱敏的真实图纸、截图、PPT 或计算结果

正式 exe 发布包应放在 `release_packages/` 或 GitHub Release，不直接进入 git。

## 测试规则

重要修改提交前运行完整测试：

```powershell
$env:PYTHONPATH='src'
.\.venv_step01_build\Scripts\python.exe -m unittest discover -s tests -v
```

只修改 Step02 时至少运行：

```powershell
$env:PYTHONPATH='src'
.\.venv_step01_build\Scripts\python.exe -m unittest discover -s tests -p 'test_part_script.py' -v
```

只修改 Step04 时至少运行：

```powershell
$env:PYTHONPATH='src'
.\.venv_step01_build\Scripts\python.exe -m unittest discover -s tests -p 'test_main_frame_assembly.py' -v
```

## CADtoCAE 专属验证

修改 Step02 后必须确认：

- 不再生成外部 `<project_prefix>_components.json`
- `<project_prefix>_create_parts_in_cae.py` 内嵌 `COMPONENTS_JSON`
- Abaqus Model 名等于 `<project_prefix>`
- 不自动打开或保存 `.cae`
- 调试报告进入 `过程文件\调试文件`

修改 Step04 后必须确认：

- 输入为 `<project_prefix>_coordinate_formula_simple_fixed.xlsx` 和 `<project_prefix>_create_parts_in_cae.py`
- 输出为 `<project_prefix>_assembly_frame.py`
- 不生成外部 `assembly_inputs.json`
- 调试报告进入 `过程文件\调试文件`
- 脚本只操作同名 `<project_prefix>` Model
- 不生成多余 RP/reference point
- `INCLINED_BEAM` 装配时额外绕自身中心轴旋转 180°

涉及真实流程时，应重跑 `real_tests` 中 ANG18 和 ANG33 样例。

## 分支建议

- `feature/step02-all-components`
- `feature/step04-sp-dc-dp-assembly`
- `feature/step05-analysis-submit`
- `fix/step04-coordinate-error`
- `docs/user-manual`

