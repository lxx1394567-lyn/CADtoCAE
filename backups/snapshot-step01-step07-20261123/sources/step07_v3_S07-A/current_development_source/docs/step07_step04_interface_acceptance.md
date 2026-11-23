# Step07 V0.3.2 Step04 输入接口验收记录

本轮仅 Step07-1。技术验证通过，等待人工打开 CAE 验收。没有开发阶段 2～5，没有提交 Job，没有修改 BatchRunner 或 Step02～06。

## 交付

- EXE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe`
- 已执行验证脚本：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\s4\input\Step07_Results\Batch_20261017_100851_8c11aedc\S1_8aad9e34\SP_SC_ANG18_11042210101041S-T0202_step07_01_step.py`
- 输出 CAE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\s4\input\Step07_Results\Batch_20261017_100851_8c11aedc\S1_8aad9e34\SP_SC_ANG18_11042210101041S-T0202_step07_01.cae`
- 另留一份尚未执行、可供 File → Run Script 检查的脚本：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\s4\input\Step07_Results\Batch_20261017_101032_a3875be3\S1_e7a74b63\SP_SC_ANG18_11042210101041S-T0202_step07_01_step.py`

## 真实输入和结果

ANG18 输入来自 BatchRunner 20261011-092525-4a315a0d 的 step2/checkpoint.cae。job.json contract.kind=assembly，receipt SUCCESS，二者 token 一致，9 Parts / 15 Instances。复制到本 Worktree 隔离测试目录；.source.json 记录原路径、阶段证据及 SHA256。此模型为 Step04 装配调试模型，尚不具备 Step05/06 连接工程验收条件。

真实冻结 EXE 启动 Tk 界面，通过 --ui-smoke 调用默认生成按钮。日志证明 GENERATED、输出 CAE 数量 0；生成测试特意配置不可用 ABAQUS 命令，仍正常生成。随后 ABAQUS 2020 cae noGUI 从不同工作目录运行 EXE 生成的原始 PY，保存并重新打开 CAE：SETUP_COMPLETE、preservation PASS、reopen PASS。摘要实例核对 PASS；输入及原始 checkpoint SHA256 均不变。

新增 STEP07_STATIC，Static General，NLGEOM OFF，初始/最大增量 1，最小增量 1e-7，最大步数 1000，时间 1。新增 BC/Load/节点/单元/Job 全部为 0。原有模型清单、几何、网格、命名区域和连接快照保持一致。不加 RP 转动约束，不修复 Tie。

实际 EXE 扫描 20261015 文件夹：识别 8 个项目，6 个可生成；2 个 DP 项目存在不同内容的多个无明确阶段记录的 CAE，正确报告歧义。没有因缺少荷载跳过项目。未运行这些项目的分析。

30 项自动化测试通过（接口/防误配/来源优先级/重复版本/仅生成/原有核心回归）。这些测试不等同于支架工程验证。旧求解诊断测试仍有读取日志未关闭句柄的 ResourceWarning，不影响本轮测试结果；本轮未改旧求解流程。

71 个上游快照文件哈希全部一致；构建清单与当前代码哈希一致。旧 GUI/EXE、核心验证模型及备份保留，未提交或推送。

## 人工验收与限制

在 ABAQUS/CAE 2020 中先保存当前会话，再 File → Run Script 运行上述尚未执行脚本；脚本自动打开记录输入，输出独立 CAE 和报告。成功后人工查看计算步与原模型。已执行的验证脚本因输出存在会拒绝覆盖，重测需在 EXE 重新生成。

尚未通过人工菜单点击进行验收；当前真实执行证据是 ABAQUS 2020 noGUI，同一脚本入口和 runtime。未知来源显示 UNKNOWN，不声称 Step05/06 已完成。非编号文件名需要可选来源记录；有多版本歧义时须人工整理或补充可信阶段记录，程序不按修改时间猜测。任何结果均 DEBUG_MODEL / engineering_verified=false。

阶段 2～5 只有统一命名占位且禁用。本轮到此停止，等待用户验收。
