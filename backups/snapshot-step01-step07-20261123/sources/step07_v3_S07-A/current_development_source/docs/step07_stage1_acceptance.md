# Step07-1 计算步阶段验收记录

2026-10-16，V0.3.0。当前状态：自动测试通过，等待人工检查。只开放阶段 ①；②～⑤ 禁用，未开发或运行其阶段入口。没有人工验收通过前不继续。

## 环境与交付

工作区：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development`；分支 `feature/step07-analysis-setup`。没有新建 worktree、修改 Step02～Step06、提交或推送。调整前 Step07 代码保存在 `step07_runs/backups/before_stage1`。

EXE：`dist/CADtoCAE_Step07_AnalysisSetup/CADtoCAE_Step07_AnalysisSetup.exe`，SHA256 `1b5b08ccd9533acdef8d1b53b0919fa63b2923ad761f6e020a9fdfdf2859c84a`。需保留完整同名目录，包括 `_internal`。使用说明见 `step07_gui_usage.md`。

## 实现范围

GUI 沿用文件夹扫描和项目清单，仅增加五阶段显示，只有 ① 计算步可用。扫描只要求 CAE 和匹配的 Assembly Summary，不读取或要求荷载和连接计划。精确按摘要 model_name 定位目标 Model；找不到即报错。

`step07_setup.py::generate_stage1` 生成独立阶段脚本，`step07_runtime.py::run_step07_stage1` 只调用 StaticStep，保存并重开核查。已有全流程函数保留，但阶段入口不调用它们。内部参数仍在 `step07_rules.py`，无需 GUI 填写。

目标 Model 只允许 Initial；已存在分析步会 FAILED，不重复创建或覆盖。输入复制后再打开，前后校验原始 SHA256。ABAQUS 自动附带的新默认 Field/History Output 请求会移除，以保持输入原有请求仓库；处理记录在阶段报告中。

## ANG18 实际 EXE 测试

输入目录 `step07_runs/s1/input` 只有配套 Assembly Summary 和完整编号_final.cae，没有荷载或连接计划 JSON。CAE 是此前已完成 Step06 连接更新的 `upstream_completed.cae` 的副本，没有在本阶段重放更新。

通过最终打包 EXE 的 GUI 回调回归入口执行，frozen=true，事件循环轮询 40 次，SUCCESS=1。调用实际 GUI 扫描/运行回调和后台线程，实际运行 ABAQUS 2020；不是仅测试 Python 源码。原生文件选择对话框的人工点选体验尚待用户确认。

输出 CAE：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\s1\input\Step07_Results\Batch_20261016_170640_ab33c26e\S1_1bead5c7\SP_SC_ANG18_11042210101041S-T0202_Step07-1_Step.cae`

计算步：`STEP07_STATIC`，Static General，NLGEOM OFF，总时间 1，初始增量 1、最大增量 1、最小增量 1e-7、最大增量步数 1000。保存后关闭模型数据库，并使用 ABAQUS 2020 openMdb 重新打开，核验步骤类型、参数和步骤列表，结果 PASS。

保存前与重开后的模型数据比对 PASS：Part/Instance 几何与已有网格、装配位置、RP、Set/Surface 成员、Tie/Coupling 等连接属性、Connector 数量、BC/Load/Interaction/Job 等仓库保留。新增统计：Step=1，BC=0，Load=0，节点=0，单元=0，Job=0。注意保留了上游已有的网格数据，并非将其清空。没有生成 INP/ODB、没有求解。

输入哈希前后相同：`8f347fbf96c6ef6c1fd6704b36337bfe65c12c743d2fe2eebbf0116d12bd4d6d`。

阶段报告与日志在输出目录中：`step07_report.json`、`setup_20261016_170640_05a279.log`；批次根目录有 `batch_report.json`、`desktop_session_report.json`。开发验收证据：`step07_runs/s1/exe_report.json`、`acceptance_audit.json`、`gui_success.png`。

## 其他检查与边界

- 22 项自动化测试通过，日志 `step07_runs/s1/tests.log`；包含阶段 1 不要求荷载/连接、无效荷载不阻塞阶段 1、未开放阶段拒绝及既有扫描回归。
- 将已生成计算步的真实 CAE 再作为输入执行，正确报 `EXISTING_ANALYSIS_STEP_CONFLICT`，没有保存第二份阶段成果。证据 `step07_runs/s1/conflict_test.json`。
- 首轮开发中已修复默认输出请求自动新增、Abaqus StaticStep 类型读取和快照 SymbolicConstant 序列化差异；最终 EXE 已包含这些修正。
- 这是计算步设置与数据保留验证，不是网格质量、连接力学有效性或求解验证。原 ANG18 连接问题保持原样。
- SP_DC/DP、中文路径/模型名尚未本阶段实测；版本歧义和长路径仍会明确报错。

阶段报告明确标记 `human_review=PENDING`、`automatic_next_stage=false`。请人工打开上述 CAE 检查；只有明确验收通过后才启动 Step07-2。
