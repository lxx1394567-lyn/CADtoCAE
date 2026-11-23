# Step07 首例验证结果（2026-10-16）

## 结论

ANG18 单桩单立柱的 Step → BC → Mesh → Load → Job → CAE → ABAQUS/Standard 静力求解 → ODB 校核已打通。
最终状态为 **VERIFIED_WORKFLOW_ONLY**，仅代表已明确附加边界的流程算例，不是未经简化的工程设计模型。

## 可核查产物

以下路径相对于本 Step07 Worktree：

- `step07_runs/final_validation/step07.cae`：分析设置后的模型。
- `step07_runs/final_validation/Step07_ANG18.odb`：已完成计算的结果数据库。
- `step07_runs/final_validation/Step07_ANG18.inp`：实际求解输入。
- `step07_runs/final_validation/Step07_ANG18.sta`、`.log`、`.msg`、`.dat`：原始求解证据。
- `step07_runs/final_validation/step07_report.json`：最终报告，包含独立复核 PASS、载荷坐标、网格统计、全部附加约束、反力矩及警告。
- `step07_runs/final_validation/step07_verify_results.py`：可再次执行的只读 CAE/ODB 复核脚本（仅更新报告）。
- `step07_runs/reproducible_run/step07_analysis_setup.py`：最新生成器输出的可复跑脚本，输出到独立新目录。
- `docs/step07_analysis_setup.md`：接口、模块划分、运行方式及后续计划。
- `docs/step07_upstream_snapshot.json`：Step06 开工快照 71 文件的 SHA256。

最终物理求解成功后，修正了 ABAQUS 2020 noGUI 日志格式、ODB 字符串类型和 NumPy 数值 JSON 序列化适配，并用最终复核代码重新读取实际 ODB 验证。此前误报失败的报告保留在 `step07_report.before_reverification.json`，不隐去历史记录。未重新计算或修改该 ODB。

## 算例设置及结果

| 项目 | 值 |
|---|---|
| 求解器 | ABAQUS/Standard 2020 |
| 分析 | Static, General；NLGEOM=OFF |
| 单位 | m–N–Pa |
| 载荷目标 | PURLIN_LOCAL_01 / STEP06_RP_P01_PURLIN |
| 全局位置 / m | (-1.7834522377, 0.0200000000, 2.6192164743) |
| 力 [Fx,Fy,Fz] / N | [0,0,-100] |
| 基础 | COLUMN_DOWN_01 最低 Z=0 的壳边，54 个节点，Encastre |
| 构件网格节点 | 53,326（不含装配 RP） |
| 单元 | 36,148（含 10 个 CONN3D2） |
| 完成增量 / 平衡迭代 | 1 / 2 |
| 最终时间 / ODB 帧数 | 1.0 / 2 |
| 最大位移 | 0.001374535777 m，约 1.375 mm |
| 基础反力 [Fx,Fy,Fz] / N | [0, 0.0000003427, 99.9999899864] |
| 合力相对残差 | 1.00194×10^-7 |
| 分析阶段警告 / 错误 | 0 / 0 |

采用 S4R/S3 壳和 C3D10 实体；全局尺寸 0.05 m，孔边局部尺寸 0.008 m，COLUMN_DOWN/HOOP 为 0.008 m，COLUMN_UP 为 0.025 m，PURLIN_SUPPORT 为 0.005 m。

## 已授权假设和必要修正

1. 用户明确授权四个檩条局部段 RP 固定 UR1/UR2/UR3，以代表未建模的连续檩条转动约束。
2. 用户另明确授权四个檩托梁侧 RP 固定 UR1/UR2/UR3。共 8 处附加转动边界，默认配置中不开启。本次 P01_SUPPORT_BEAM 的 Y 向反力矩约 -0.112212 N·m，其余附加 RP 反力矩接近零；仍不得据此忽略模型简化。
3. 上下立柱原 Tie 的 COMPUTED 容差随网格细化而漏绑。依据上游连接计划并核验 CAE 圆柱面半径 0.06225 / 0.06825 m，将此原有 Tie 容差显式设置为 0.00601 m。其区域、其他 Tie/Coupling 参数、RP、Set/Surface 和 Connector 保留。
4. 原保存 CAE 缺少后续 Step06 更新，已在副本上使用原有 Step06 脚本重放耦合规则、螺栓刚度预设及抱箍—斜撑连接，另存 upstream_completed.cae。未覆盖用户原始 CAE。

## 未解决的工程验证项

- 输入处理阶段有 38 条警告，其中 **118 个未 Tie 节点全部位于 INCLINED_BEAM_01**，属于斜梁局部 Tie 区域，需进一步审查区域覆盖和真实连接意图；上下立柱漏绑已消除。
- 存在输入网格质量/输出适用性等警告，未开展网格收敛与工程承载力验证。
- Connector 刚度仍是上游的流程预设，未进行工程校准。
- SP_DC/DP 已按真实角色定义 1/2 个基础候选识别，但尚未完成这两类的真实静力求解验收；首版只支持已有 Step06 加载 RP，任意坐标新 RP/Coupling 尚未开发。
- 未开发 GUI 或构建 EXE。

## 自动化与 Git

- 全量回归：572 项，OK，2 项因样例资源不可用跳过；后续仅调整结果校核后，Step07 专项 8 项全部通过，并在真实 ABAQUS 2020 中重新通过 ODB 复核。
- 测试使用 Step06 既有构建解释器（openpyxl 3.1.5），测试工作目录为本 Worktree。默认 Anaconda 环境的旧 Excel 库及临时文件清理错误单独保留日志，不作为通过依据。
- 分支：`feature/step07-analysis-setup`。
- Worktree：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development`。
- Git 基线：`ff322e1fda786378aa17f5f31690d280537c9928`。Step06 尚无提交，使用开工快照，不声称 Git 基线包含 Step06。
- 没有 commit、push 或 PR；Step02～Step06 快照文件在本 Worktree 未修改。

下一步：先审查首例的局部 Tie 警告与实际转动约束，再用完整 Step06 输出验证 SP_DC/DP，最后进入简洁 GUI/EXE。
