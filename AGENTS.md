# CADtoCAE Codex 操作规则

本文件仅记录 CADtoCAE 仓库的通用开发约束。详细 Git、worktree、测试和 EXE 构建流程见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 基本原则

1. `main` 工作区只用于同步 `origin/main`、集成验证、PR 合并后的最终检查、正式 EXE 构建和 Release。
2. 每个独立开发任务使用一个独立的 `feature/*` 或 `fix/*` 分支，并创建独立 worktree。
3. 不在 `main` 上直接开发普通功能或修复。
4. 影响 Step01、Step02、Step04 程序行为、GUI、输入输出、打包结果或运行逻辑的修改，遵循：源码修改、自动化测试、构建对应模块开发版 EXE、等待用户人工验证、再进入提交流程。
5. 未经用户明确说“测试通过，可以提交”或同等意思，不 commit、不 push、不创建 PR。
6. feature/fix worktree 中生成的 EXE 只作为开发验证版；正式集成版或发布候选版 EXE 必须在最新 `main` 上重新构建。

## 开工前检查

开始任何开发或提交前，先确认当前 Git 环境：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status
git worktree list
git remote -v
```

必须确认当前目录是本任务指定的独立 worktree，当前分支是本任务指定的 feature/fix 分支，工作树状态符合预期，并且没有误操作 `main`。

## 禁止操作

除非用户明确授权，不执行：

- `git reset --hard`
- `git clean`
- force push
- 删除 branch
- 删除 worktree
- 直接 push 到 `main`
- 自动 merge PR

## 测试与 EXE

Codex 负责修改源码、运行相关自动化测试，并在修改影响 Step01、Step02 或 Step04 程序运行时构建对应模块的开发版 EXE。用户负责实际运行 EXE，检查 GUI、输入输出文件和 Abaqus 中的最终效果。

开发阶段的 EXE 输出应位于当前 worktree 自己的构建输出目录，例如 `dist/`，避免不同 worktree 的生成物混淆。

纯文档、Git 流程说明等不影响程序运行的修改，不强制构建 EXE。

## 提交前

提交前必须检查修改范围并运行最终相关测试：

```powershell
git status --short
git diff --stat
```

第一次 push 新分支时应建立远程 tracking branch：

```powershell
git push -u origin <当前branch>
```

