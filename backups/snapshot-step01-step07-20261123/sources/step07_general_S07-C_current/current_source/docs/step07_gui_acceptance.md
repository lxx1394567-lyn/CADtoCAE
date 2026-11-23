# Step07 GUI/EXE 验收记录（2026-10-16）

## 交付与验收边界

独立 Windows EXE 已构建且真实启动。桌面自动化点击未能触发 Tk 控件；重连后仍无效果。因此不能宣称“通过 EXE 手工选文件并执行”的完整验收已经通过，已请求用户在已打开的 GUI 中点击一次运行。下面明确区分真实 EXE 启动、源码服务集成检查、人工验收。

工作区：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development`。

分支：`feature/step07-analysis-setup`；Git 基线 `ff322e1fda786378aa17f5f31690d280537c9928`，上游 Step06 未提交快照来源见 `step07_upstream_snapshot.json`。未新建 worktree，未提交、推送或修改其他 Step 分支。

EXE：`dist/CADtoCAE_Step07_AnalysisSetup/CADtoCAE_Step07_AnalysisSetup.exe`。

EXE SHA256：`A14234F539D5363F32AE955E58E018C89CEB705369D3A5D3FD9ACAFD7A375267`。

打包内容和源文件哈希：同目录 `build_manifest.json`。构建日志：`step07_runs/gui_build_final.log`。启动截图：`step07_runs/gui_acceptance/01_startup.png`。

## 已完成检查

| 检查 | 结果与证据 |
|---|---|
| 真实打包 EXE 独立启动 | 已启动，窗口标题 CADtoCAE Step07 0.1.0，路径与交付 EXE 一致；窗口响应状态 True |
| GUI 初始布局 | 输入路径、三页参数、日志和两阶段按钮可见；提交按钮初始禁用 |
| 自动化测试 | 13 项通过，`step07_runs/gui_tests_final.log` |
| 源码服务执行真实 ABAQUS 2020 设置 | SETUP_COMPLETE；使用与 GUI 相同的 new_run / execute 和分析核心 |
| 特殊设置关闭 | 0 个附加转动约束，未调用 Tie 修正；无 Step06 更新重放 |
| 模型保存与重新打开 | 新 CAE 在 ABAQUS 2020 noGUI 中重新打开并查询成功 |
| 输入不覆盖 | 输入 SHA256 在前后保持一致，运行报告 upstream_unchanged=true |
| EXE 文件选择 / 按钮执行 | 待人工确认，不能用源码集成测试替代 |
| EXE 长时间运行期间交互 | 后台线程实现已完成，尚待真实按钮运行记录验证 |

## ANG18 默认设置集成测试

输入为上一阶段已完成连接更新的本地模型 `step07_runs/upstream_completed.cae`，不是 GUI 自动更新的原始模型。配套摘要和连接计划位于 `CADtoCAE-EXE-Testing/step06test2`。人工测试配置为 `step07_runs/gui_acceptance/ANG18_gui_config.json`；其旧转动开关刻意保留 true，用于检查 GUI 普通载入会重置为关闭，不能直接把这个原始配置当成默认安全命令行配置执行。

此次服务测试显式关闭两个转动开关和 Tie 修正。输出目录：

`step07_runs/gui_acceptance/service_results/Step07_20261016_161813_cd077a4f`

- 新模型：`step07.cae`。
- 报告：`step07_report.json`、`reopen_check.json`；日志：`setup_20261016_161813_8f1991.log`、`reopen_check.log`。
- 输入 SHA256：`8F347FBF96C6EF6C1FD6704B36337BFE65C12C743D2FE2EEBBF0116D12BD4D6D`。
- Static, General：`STEP07_STATIC`，NLGEOM 关闭，初始/最大增量 1、最小增量 1e-7、最大增量步数 1000。
- 基础：`COLUMN_DOWN_01`，z=0 m，54 个固定节点。
- 网格：53,326 个节点；36,138 个构件单元，加 10 个装配 Connector，报告共 36,148 个单元。
- 荷载：`PURLIN_LOCAL_01` → `STEP06_RP_P01_PURLIN`，全局力 `(0,0,-100)` N，RP 坐标约 `(-1.78345224,0.02,2.61921647)` m。
- Job：`Step07_ANG18`，仅创建并写 INP，未提交；无 ODB。
- 连接保留检查 PASS；重新打开确认 Tie 方法仍为 COMPUTED。

此测试证明新桌面执行服务能够调用真实 ABAQUS 并保存可重开的 CAE，但不代表通过 EXE 按钮完成了操作，也不代表默认模型已可稳定求解。

## 人工验收操作

在交付 EXE 选择上面的 ANG18 配置（自动带出配套路径），检查三个特殊设置全部关闭，点击“① 生成并运行分析设置”。输出应在 `step07_runs/gui_acceptance/results/Step07_*`；成功后会生成 `desktop_session_report.json`，记录 frozen=true、EXE 路径、界面轮询次数和执行结果。再在 ABAQUS 2020 中打开本次 `step07.cae` 检查。无需点击提交按钮。

## 已知限制

详见 `step07_gui_usage.md`：SP_DC/DP 尚未完整验收；当前只支持现有 Step06 标准 RP；中文路径未验收；不自动处理已有分析步/荷载/边界。ANG18 原有自由转动、Tie 和未 Tie 节点问题没有通过 GUI 开发被消除。默认设置成功不等于求解通过，也不等于工程验算合格。
