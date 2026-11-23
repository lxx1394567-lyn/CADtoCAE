# BatchRunner 交付与验证记录

日期：2026-10-11。开发验证版，尚未提交 Git。
分支 feature/batch-runner；基线 main a0092c0。
目录 F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-BatchRunner。
main 工作区最终检查干净。其他开发 worktree 仅作只读源码审查。

## 阶段交付

| 阶段 | 实现 | 文件 | 验证与限制 |
|---|---|---|---|
| 1 审查 | 真实生成/执行依赖、模型传递、REPORT 别名、新版 Connector 的孔报告依赖；方案 C | batch_runner_audit.md | 未把全部 Excel/JSON 误设为必需；未合并或修改 Step 业务算法 |
| 2 CLI | 扫描、连续计划、输入声明、项目选择、串行运行、失败阻塞、JSON/CSV/控制台日志 | scanner.py、dependencies.py、executor.py、runner.py、cli.py、scripts/batch_runner.py | 9 项目串行及失败/缺失边界模拟通过；未知脚本需明确契约 |
| 3 检查点 | CAE 副本恢复、模型验证、SHA256、下游失效、full/resume/from、当前孔报告传递 | state.py、cae_worker.py、runner.py | 真实 Abaqus 三阶段保存/重开、resume、从第 3 步重跑通过；不在最终模型上叠加重跑 |
| 4 GUI/EXE | Tkinter 目录、勾选、状态、模式、启动/安全停止、记录查看；GUI 与 CLI 独立 EXE | gui.py、batch_runner_gui.py、build_batch_runner_exe.ps1 | GUI EXE 隐藏窗口初始化/事件循环冒烟通过；完整人工点击验收尚未进行 |

下一阶段：使用实际项目对 5 阶段结果进行人工验收，尤其是 Step05 规则、开孔几何和 Connector。

## 自动化测试

- 专项 tests/test_batch_runner.py：32 项通过。
- 完整仓库回归：运行 191 项，190 通过、1 跳过，零失败。
- 跳过项：test_step01_pdf_only_does_not_fake_components，原因 sample PDF is not available。
- 完整记录：outputs/regression_final.log；专项记录：outputs/batch_tests_final.log。
- 新增测试覆盖全部 17 类需求场景及 REPORT 别名、集成孔报告隔离、嵌套报告错误、
  实际执行器的异常退出/缺失 receipt/错误 token、强制重跑失败后的历史失效。
- FakeExecutor 文件明确标记 SIMULATION ONLY，不构成真实 CAE 证据。

## 真实 Abaqus 2020 验证

调用本机 abaqus.bat，成功取得 CAE 许可证；生成真实 CAE 并保存后重新打开。
合成模型：当前 main 的 Part 生成器创建小型角形壳 Part；测试装配脚本创建实例；
测试分析脚本创建 StaticStep。后两脚本是明确声明契约的合成冒烟脚本，
不是完整支架的 Step04/Step05 业务算法验证。

源码版：outputs/batchrunner-integration/d25d2cfd84/validation.json。
完成 full → resume（3 步全部复用）→ from 3（恢复第 2 步，重建分析步）。
中文项目源目录、空格、中文结果目录均已验证。第 4/5 步缺失正确标记 MISSING，
项目汇总为 PARTIAL_SUCCESS。

发现 Abaqus 2020 在中文 cwd 下可能在 Python 启动前退出，执行器使用 ASCII 临时目录，
最后归档回中文结果目录。所有输入和上游 CAE 都先复制；包装器不打开用户原始模型进行修改。
Python 2 的仓库键转换、Windows BAT 参数传递已通过实际启动验证。

CLI EXE：outputs/EXE 中文运行/20261011-083248-13750158/summary.json。
通过打包后的程序再次完成同一合成模型的 3 阶段真实运行。
EXE 扫描：outputs/exe-scan/scan.json；GUI EXE 初始化：outputs/gui_exe_smoke.json。

## 构建

构建 Python：相邻 main 已有 .venv_step01_build 的解释器（只使用已安装依赖，不安装或修改其源码）。
PyInstaller 6.22.2；Tcl/Tk 8.6；复用已有 Tcl/Tk DLL 检测方式。
构建日志：outputs/build_final.log。

- dist/CADtoCAE_BatchRunner/CADtoCAE_BatchRunner.exe
- dist/CADtoCAE_BatchRunner_CLI/CADtoCAE_BatchRunner_CLI.exe

两个程序均为 onedir 包，分发时必须携带整个对应目录（含 _internal），不能只复制 EXE。
全部生成物位于本 worktree 的 dist、build、outputs。

## 尚未验收的边界

1. 用户实际 9 套支架完整 5 阶段尚未进行真实批量验收。
2. 新版 Step05/Step06 来自其他工作区只读审查；其生成接口适配已有专项测试，
   真实复杂模型的几何、连接和工程正确性不由合成冒烟代替。
3. 任意动态 Python 的依赖无法完全静态推断；只执行可信建模脚本，未知接口需要 manifest。
4. 输入 Excel/计划变化会使检查点失效，但调度器不会替用户重新生成内嵌数据的 PY。
5. 安全停止按阶段边界执行，不强杀卡在许可证/内核或正在保存数据库的进程。
6. GUI 已做启动级检查，完整操作和模型效果留待人工验收。暂不 commit、push 或 PR。
