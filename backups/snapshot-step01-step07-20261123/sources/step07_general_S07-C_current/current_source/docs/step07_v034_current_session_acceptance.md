# Step07 V0.3.4 当前会话修复及技术验证报告

当前状态：技术探针通过；真实用户 GUI 会话尚待人工验收。仅 Step07-01，后续阶段禁用。未修改 BatchRunner、Step02～06，未提交或推送。

## 根因

旧版使用 openMdb 读取磁盘副本替换当前 MDB，并在保存、重新打开校验时关闭 MDB。版本仅在生成阶段分配，运行时不递增。现场 v2_report.json 记载一次保存之后的 UPSTREAM_CHANGED 失败；输出 v2.cae 已经存在，再运行固定路径 v2.py 被正确拒绝。不能把 OUTPUT_EXISTS 当作关闭覆盖保护的理由，也不能根据日志确定旧文件变化的唯一原因。

另行探针确认 ABAQUS saveAs 可改变当前磁盘 MDB 的字节。该探针重开旧源模型仍为 Initial，原模型库存保持一致；所以哈希变化不能直接认定为丢失连接，但也不能承诺文件逐字节不变。

## 交付

- EXE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\V0.3.4\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe`
- 用户本次应运行的新 PY（尚未执行）：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01_step_v4.py`
- 该脚本预定输出（尚未生成）：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07_01_v4.cae`
- 该脚本内存模型恢复备份：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07_01_v4_before_step.cae`

请运行新版文件，不要继续运行旧 v2/v3。文件名版本只在生成时分配；如果路径随后被占用，运行前停止并要求重新生成，不自动改号，不覆盖已有输出。

## 模式和恢复保护

默认 PY execution_mode=CURRENT_SESSION_DEBUG：只访问当前 abaqus.mdb，以完整 project_id 精确寻找 Model，不存在或已有计算步均停止；不调用 openMdb/close，不回放前序脚本。保存前打印准确路径。对于已保存的当前 MDB，先复制原磁盘字节到 _before_step_disk.cae，再 saveAs _before_step.cae 记录当前内存模型，随后只创建 STEP07_STATIC。检查成功才 saveAs 阶段输出，当前 MDB 保持打开；保存后其路径指向新文件。

共用 s7_apply_static_step；独立模式 INDEPENDENT_CAE 才在新进程加载磁盘 CAE 并重开校验。模式写入 PY/plan/report，自动入口拒绝当前会话脚本，防止静默改成加载磁盘。当前会话报告 input_cae_used=false，扫描得到的磁盘来源仅供参考，不代表当前内存模型已执行哪些上游步骤。

参数检查失败时删除本次新增计算步、清理自动新增输出请求，并核对原模型库存及步骤列表；失败状态不静默保存为阶段成果。回退无法确认时报告 FAILED_USE_PRE_STEP_BACKUP。如果原生保存过程中留下部分输出，报告失败且不复用其文件名。

重要限制：原生 saveAs 可能改变“当前打开的原 CAE”字节，本程序记录前后哈希及警告，保留原始磁盘字节副本，不擅自回写旧文件。严格要求原文件逐字节不变时，请在专用工作副本会话中人工调试。已有 Step07 历史输出版本未被覆盖或删除。

## 验证

36 项自动化测试通过。真实冻结 EXE 生成两种模式脚本。

ABAQUS 2020 使用已保存的 test.cae 的隔离副本模拟已有当前会话，识别目标 DP_ANG14，9 Parts / 17 Instances / 30 Constraints。测试期间把 abaqus.openMdb 替换成必定报错的守卫，实际当前模式入口仍成功，执行后 MDB 对象身份不变，目标模型仍存在，连接及几何快照不变，新增 STEP07_STATIC，新增 BC/Load/节点/单元/Job 均为 0。

验证目标不存在不回退加载、同名步停止、输出占用在修改前停止；注入参数检查失败后回退通过，保留恢复备份，不产生阶段 CAE。原磁盘字节副本哈希核对通过。

另一个独立进程重开当前模式结果，步骤参数及库存均 PASS。独立 CAE 模式真实 EXE 自动执行也 PASS，两个模式参数完全一致。当前脚本报告 reopen=PENDING_EXTERNAL_VERIFICATION，额外重开结果在 external_reopen_final.json，不伪装在用户 GUI 内执行了重开。

真实 GUI 验证未完成：Windows 工具返回 Computer Use app approval timed out，没有在用户桌面执行脚本，也未关闭用户 MDB。以上 session_alive 是独立进程的当前 MDB 探针证据，不能冒充用户 GUI 测试。

验证 CAE、阶段报告位置见 step07_runs/v034/acceptance_audit_final.json 的 current_session_probe。工程验证仍为 false。

## 文件审计

71 个上游源码快照哈希不变；已有 Step07 输出哈希不变。期间观察到 11:06 的另一个 BatchRunner 批次更新了历史记录及 Step04 CAE；本任务未启动该批次、未修改这些文件，不能声称整个工作目录在测试期间完全静止。具体差异记录在 acceptance_audit_final.json。

本轮已停止，等待用户人工验收，不进入 Step07-02。
