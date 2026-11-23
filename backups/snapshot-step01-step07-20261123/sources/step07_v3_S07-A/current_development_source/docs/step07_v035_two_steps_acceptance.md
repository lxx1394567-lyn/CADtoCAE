# Step07 V0.3.5 两个连续静力计算步验证报告

只更新 Step07-01，不施加预紧力、外荷载，不创建 BC、Mesh、Job，不开发后续阶段。继续原 Step07 Worktree/分支，未修改 Step02～06 或 BatchRunner，未提交、推送。

## 交付

- EXE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\V0.3.5\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe`
- 待人工执行 PY（尚未执行）：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01_step_v5.py`
- 该 PY 预定输出（尚未生成）：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07_01_v5.cae`
- 已验证的隔离测试 CAE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\v035\fixture\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07_01.cae`
- 模型保留及阶段报告：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\step07_runs\v035\fixture\DP_ANG14_FA03521S-T0104-02_step07_01_report.json`

## 两步参数（真实 ABAQUS 2020 保存后重开读取）

| Name | Previous | Procedure | NLGEOM | Time Period | Incrementation | Initial | Minimum | Maximum | Maximum increments |
|---|---|---|---|---|---|---|---|---|---|
| STEP07_PRELOAD | Initial | Static General | OFF | 1 | AUTOMATIC | 0.01 | 1e-7 | 1 | 1000000 |
| STEP07_LOADING | STEP07_PRELOAD | Static General | OFF | 1 | AUTOMATIC | 0.01 | 1e-7 | 1 | 1000000 |

构造函数明确传递 previous；保存后读取步骤顺序和所有参数复核。第二步继承第一步结束状态，未创建或施加任何实际预紧力/荷载。

## 技术验证

37 项自动化测试通过。真实冻结 EXE Tk 回调测试生成 CURRENT_SESSION_DEBUG 脚本；用用户 v4_before_step.cae 的隔离副本进行 ABAQUS 2020 当前会话探针。目标 DP_ANG14 的原 30 个约束及模型库存快照保留；MDB 对象身份不变，目标 Model 仍在，执行期间禁止 openMdb 的守卫未触发。只新增两步，BC/Load/节点/单元/Job 新增数全为 0。

测试目标缺失、输出路径已占用、同名新步骤冲突及旧 STEP07_STATIC 冲突，均停止且不删除旧步骤。注入第二步创建失败，确认第一步也回退，步骤列表恢复 Initial，没有阶段 CAE；两步创建后的参数检查失败也成功回退。

独立进程重开当前模式 CAE，preservation PASS、reopen PASS。真实 EXE 的 INDEPENDENT_CAE 自动执行亦通过，两个模式参数完全一致。此证据是 noGUI/已有 MDB 的技术探针，不冒充本轮用户在 Step Manager/Edit Step 窗口中的人工验收。

71 个上游源码快照文件哈希不变。工作目录原有文件核对数量及差异见 step07_runs/v035/acceptance_audit.json；历史成果未删除、未用于测试覆盖。本轮源文件修改前备份位于 step07_runs/backups/before_v035。

## 人工操作

1. 新版脚本不会自动升级旧 PY。请使用本报告列出的待运行 PY，或启动 V0.3.5 EXE 重新生成。
2. 当前已验收 v4.cae 中存在 STEP07_STATIC，直接运行新脚本会按要求报告冲突。先保存当前工作，再人工打开计算步创建前的模型工作副本，例如 v4_before_step.cae 的副本；核对模型完整项目编号和连接齐全、Steps 仅 Initial。
3. File → Run Script 执行新 PY。脚本不 openMdb、不 close 当前 MDB，先保存恢复副本，再创建两步并保存独立结果。查看日志中的准确输出路径。
4. Step Manager 应为 Initial→STEP07_PRELOAD→STEP07_LOADING。逐一打开 Basic 和 Incrementation 按上表验收。当前模式报告 reopen=PENDING_EXTERNAL_VERIFICATION；本轮另进程重开记录在 external_reopen.json。
5. 保留原生 saveAs 限制：它可能改变当前打开 CAE 的文件字节。已有原磁盘字节副本和内存恢复副本保护；为保持验收前成果，请在专用工作副本中调试。已有输出则生成新版本，不覆盖历史文件。

本轮停止开发，等待人工验收，不进入 Step07-02。
