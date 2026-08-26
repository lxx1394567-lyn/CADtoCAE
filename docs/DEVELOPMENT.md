# CADtoCAE 开发流程

本文档记录 CADtoCAE 仓库的通用 Git、Codex、自动化测试和 EXE 构建流程。它适用于 Step01、Step02、Step04 等模块的日常开发，不记录任何单次任务的 worktree 路径、分支名称或临时开发目标。

## 总体原则

CADtoCAE 的开发验证由 Codex 和用户分工完成：

- Codex 负责源码修改、源码检查、自动化测试，并在需要时构建 EXE。
- 用户负责直接运行 EXE，检查 GUI、输入输出文件以及 Abaqus 中的最终效果。

开发阶段的 EXE 是测试工具。正式集成版或发布候选版 EXE 必须在功能合并进入最新 `main` 后重新构建。

## 工作区职责

`main` 工作区只用于：

- 同步 `origin/main`
- 集成验证
- PR 合并后的最终检查
- 构建正式发布版 EXE
- GitHub Release 或其他发布归档

普通功能和修复应在独立 feature/fix worktree 中完成。每个独立任务使用：

```text
一个开发任务 = 一个 branch + 一个独立 worktree + 一个 Codex 对话
```

分支命名应表达任务目标，例如：

- `feature/step01-xxx`
- `feature/step02-xxx`
- `feature/step04-xxx`
- `fix/step02-xxx`

一个任务完成并合并 `main` 后，下一次新的功能修改应从最新 `main` 创建新的 branch 和 worktree，不长期复用旧 feature branch。

## 开工前 Git 检查

在任何 feature/fix 对话开始工作前，先执行：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status
git worktree list
git remote -v
```

需要确认：

1. 当前目录是本任务指定的独立 worktree。
2. 当前 branch 是本任务指定的 feature/fix branch。
3. 当前工作树状态符合预期。
4. 没有误操作主工作区。
5. 未经用户明确授权，不切换到 `main` 开发。

## Git 安全规则

除非用户明确授权，否则不执行：

- `git reset --hard`
- `git clean`
- force push
- 删除 branch
- 删除 worktree
- 直接 push 到 `main`
- 自动 merge PR

在用户明确允许提交前，不因为代码看起来正确就自动 commit。

## 功能开发循环

影响 Step01、Step02、Step04 程序行为、GUI、输入输出、打包结果或运行逻辑的修改采用以下循环：

```text
分析需求
↓
检查相关源码和测试
↓
修改源码
↓
运行相关自动化测试
↓
测试失败则修复源码并重新测试
↓
测试通过
↓
重新生成当前模块开发版 EXE
↓
告知用户 EXE 的完整路径
↓
等待用户实际运行 EXE 验证
↓
根据用户反馈继续修改或进入提交流程
```

自动化测试和人工 EXE 测试不能互相替代。只有自动化测试通过，并且用户实际验证 EXE 没有问题后，本次任务才进入提交阶段。

纯文档、Git 流程说明等不影响程序运行的修改，可只进行文档检查、必要的静态检查和 Git 状态确认，不强制构建 EXE。

## EXE 构建原则

当修改影响 Step01、Step02、Step04 的程序行为、GUI、输入输出、打包结果或运行逻辑时，开发阶段允许并推荐在当前 feature/fix worktree 中反复构建对应模块 EXE：

```text
当前 worktree
↓
修改 Step01、Step02 或 Step04 源码
↓
运行对应测试
↓
重新生成对应 Step 的开发版 EXE
↓
用户运行 EXE 检查
```

开发版 EXE 应输出到当前 worktree 自己的构建目录，例如：

```text
当前 worktree/
└─ dist/
   └─ 对应 Step 的 EXE
```

不同 worktree 不共享开发阶段的 `dist/` 和 `build/` 目录，避免不同 branch 的 EXE 混淆。

如果已有打包方式，应优先复用和规范现有方式，而不是重复创建新的打包体系。如果项目尚无稳定的一键构建方式，可在不影响现有程序逻辑的前提下逐步建立：

```text
tools/
├─ build_step01.bat
├─ build_step02.bat
├─ build_step04.bat
└─ build_all.bat
```

目标是让用户无需打开 Python IDE：

```text
Codex 修改源码
↓
Codex 自动运行测试
↓
Codex 调用构建脚本
↓
生成 EXE
↓
用户直接运行 EXE
```

## CADtoCAE 项目级回归验证

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

修改 Step01、Step02 或 Step04 的程序行为、GUI、输入输出、打包结果或运行逻辑时，应在相关自动化测试通过后构建对应模块开发版 EXE，并等待用户人工验证。

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

## 源码与生成物管理

Git 应主要管理：

- `src/`
- `tests/`
- 打包脚本
- requirements 文件
- 配置文件
- 必要示例文件

`.spec` 是否纳入版本控制应在后续统一 EXE 构建方案中单独确认；在此之前遵循当前 `.gitignore` 规则，不擅自提交 `.spec`。

开发过程中的以下内容原则上不因每次功能修改而提交：

- `build/`
- 临时缓存
- 中间产物
- 开发版 EXE
- 用户项目生成文件

如果 `.gitignore`、旧文档或项目结构与上述规则存在冲突，应先向用户说明并单独确认，不擅自大规模调整。

## 每轮修改后的汇报格式

完成一轮修改后，向用户汇报：

### 修改内容

说明修改了哪些功能和源码文件。

### 自动化测试

说明运行了哪些测试以及结果。若存在跳过或失败，必须明确说明。

### EXE 构建

若本轮修改影响 Step01、Step02 或 Step04 的程序行为、GUI、输入输出、打包结果或运行逻辑，说明：

- 是否成功
- 构建的是 Step01、Step02 或 Step04 中哪个程序
- EXE 完整路径
- 是否为当前 feature/fix branch 最新源码生成

若本轮修改不影响程序运行，说明未构建 EXE 的原因。

### Git 状态

说明：

```text
当前 branch
当前 worktree
git status
```

### 下一步

默认写：

```text
等待人工运行 EXE 验证，暂不 commit。
```

## 人工验证通过后的提交流程

只有用户明确说“测试通过，可以提交”或表达同等意思时，才进入：

```text
检查 git diff
↓
确认修改范围
↓
运行最终测试
↓
commit
↓
push
↓
创建 PR
↓
等待 PR 检查或人工确认
↓
merge main
```

第一次 push 新 branch 时应正确建立远程 tracking branch：

```powershell
git push -u origin <当前branch>
```

不要把 feature branch 设置为长期跟踪 `origin/main`。

## 合并后的正式 EXE

feature/fix PR 合并进入 `main` 后：

1. 回到 `main` 工作区。
2. fetch / pull 最新 `origin/main`。
3. 确认 `main` 工作树 clean。
4. 从最新 `main` 重新构建需要发布的 EXE。
5. 必要时构建 Step01、Step02、Step04 全套程序。
6. 进行最终集成测试。

此时生成的 EXE 才视为正式集成版或发布候选版 EXE。feature/fix worktree 中的 EXE 一律视为开发验证版 EXE。
