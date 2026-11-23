# Step07：ABAQUS 2020 静力分析最小流程

## 隔离开发与基线

- Worktree：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development`
- 分支：`feature/step07-analysis-setup`
- Git 基线：`ff322e1fda786378aa17f5f31690d280537c9928`（Step05）
- Step06 分支没有新增提交，实际功能全部是未跟踪文件。已只读复制其未跟踪文件到本 Worktree；`docs/step07_upstream_snapshot.json` 记录文件路径和 SHA256。
- 这不是声称存在包含 Step06 的 Git 提交。未经人工验证不提交，不改其他 Worktree。

## 上游接口和实际模型

沿用 `src/cadtocae`、桌面 Python 3 生成独立 Abaqus Python 2.7 脚本的架构，不引入 Excel 模板或 GUI。
输入为 CAE、`*_assembly_summary.json` 和简单 JSON 配置；可通过 `connection_plan` 读取已有 `*_analysis_plan.json`。装配摘要提供 `model_name`、`structure_type`、`instances[].canonical_role / part_name / instance_name / connection_group`。

首个模型来自 `CADtoCAE-EXE-Testing/step06test2/CAE_Results/SP_SC_ANG18_11042210101041S-T0202_final_bf6996bef83fd0af.cae`，复制为 `step07_runs/upstream.cae`。实际检查结果保存在 `step07_runs/inventory.json`：

- 指定 Model 只有 Initial，无 Load/BC；另有空 Model-1，不操作。
- 15 个装配实例，8 个实际装配 Part；另一个未装配 PURLIN Part 已有网格，不参与求解。
- 17 个 RP、21 个约束、8 条装配 Connector 线；完整 Set/Surface 名见 inventory。
- 壳体：上下立柱、斜梁、前后斜撑、檩条局部段；实体：檩托、抱箍。
- `STEP06_RP_P01_PURLIN` 至 P04 可复用，檩条局部段长度 0.05 m。
- 保存的 CAE 缺少后续 Step06 更新。`step07_runs/prepare_upstream.py` 在副本上重放原有耦合更新、刚度预设和抱箍—斜撑连接，不改原始 CAE。三个 replay_report 为 SUCCESS 后另存 `upstream_completed.cae`。
- ANG33 最新连接报告为 FAILED，未作为通过 Step06 的基准。

## 模块与执行

1. `step07_setup.py`：配置校验、角色映射、路径保护、独立脚本生成。
2. `step07_runtime.py`：实际模型预检、Static General、底部 Encastre、壳/实体网格、既有 RP 集中力、连接保留检查、Job/CAE 保存及求解验证。
3. `scripts/step07_generate_analysis.py`：命令行入口。
4. `tests/test_step07_setup.py`：错误配置、目标、重复荷载、输入保护和脚本测试。

在本 Worktree 执行：

```powershell
python scripts/step07_generate_analysis.py step07_runs/ang18.json '../CADtoCAE-EXE-Testing/step06test2/SP_SC_ANG18_11042210101041S-T0202_assembly_summary.json' step07_runs/new_run
abaqus cae noGUI=step07_runs/new_run/step07_analysis_setup.py
```

每次使用全新输出目录。生成脚本内嵌完整 Plan，可直接通过 Abaqus/CAE Run Script 或 noGUI 执行。执行目录自动切到配置的输出目录。报告是成功判断依据；ABAQUS Windows 启动器可能在内部失败时仍返回退出码 0。

## 配置契约

- m–N–Pa，`loads[].force=[Fx,Fy,Fz]` 使用全局坐标。
- `step`：`nlgeom=false`、`initialInc=.1`、`maxInc=.1`、`minInc=1e-7`、`maxNumInc=1000`，总时间 1。
- `mesh.size` 是全局尺寸，`mesh.by_role` 按角色覆盖，共享 Part 使用所有实例要求中的最小尺寸。
- 壳体 S4R/S3，实体自由四面体 C3D10。短边包括孔边及连接分区，按 `mesh.local_size` 细化。现有完整网格保留，不自动删除几何、Set 或 Surface。
- 非网格化 Connector 线保持原状，输入文件写入器生成 CONN3D2。
- 单桩底部角色 COLUMN_DOWN；双桩 COLUMN_FRONT/COLUMN_REAR，必须恰好匹配 1/2 个。使用各实例最低 Z 平面的壳边/实体面，失败即停止，不使用固定 Face ID。
- 首版加载仅支持既有 Step06 檩条 RP，并验证对应 Coupling。任意坐标新 RP/分布耦合尚未实现，缺失 RP 明确报错。
- 既有分析步、荷载或 BC 暂时拒绝，以防混入未知工况；重复运行用原始上游和新输出目录，不在旧结果上叠加。
- `job.submit` 默认 false；true 才执行求解。
- `validation_assumptions.fix_purlin_rp_rotations` 默认关闭。用户于本次开发明确授权流程算例开启：四个檩条 RP 的 UR1/UR2/UR3 固定，代表未建模连续檩条的转动约束。报告逐项记录，不能作为已校准工程模型。

## 验证与限制

成功求解要求 `.sta` 和 `.log` 均确认完成、ODB 最后一帧时间为 1、U/RF/S 非空、基础反力与输入合力相对误差 <= 1%。数值奇异、零主元、负特征值、求解错误不得记为 VERIFIED。启用附加边界的完成状态为 VERIFIED_WORKFLOW_ONLY，并输出所有附加 RP 的反力矩。

连接保留检查比较原有 Set/Surface/RP、Tie/Coupling 参数、Connector 截面分配和方向数量；保留不等于证明力学模型正确。求解器的未 Tie 节点、单元畸变等警告另行记录，仍需工程审查。螺栓刚度使用 Step06 的临时流程预设，未进行校准或网格收敛研究。

初始粗网格出现抱箍负体积单元；错误元素均涉及 Tie 自动调整，细化立柱主面网格后输入检查通过。单独细化抱箍不能解决主面离散引起的调整问题。

开发顺序：先完成 SP_SC 实算及日志验证；随后用完整 Step06 输入验证 SP_DC/DP 的约束数量和连接；最后再开发 GUI/EXE。当前未构建 EXE。

用户另明确授权 `validation_assumptions.fix_support_beam_rp_rotations=true`：每个檩托的梁侧 RP 固定 UR1/UR2/UR3。与檩条 RP 一起共有 8 处附加转动约束，默认全部关闭。它们可能承担本应通过真实结构传递的力矩，结果仅验证流程。

`connection_plan` 中上下立柱的壳中面半径为 0.06225 / 0.06825 m。细网格下 COMPUTED Tie 位置容差漏绑上立柱，故首例依据上游计划并核验 CAE 圆柱面半径后，将该既有 Tie 的容差设为 SPECIFIED 0.00601 m；不更换区域、不增设连接，修正记录在 connection_adjustments。不能将“对象还存在”当作“连接有效”。

开工快照复制后，其他任务又修改了 Step06 原目录部分文件；本 Worktree 的 71 个快照文件仍与清单一致，不混入并行修改。

API 背景参考：[Abaqus Coupling 文档](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECSTRefMap/simacst-c-coupling.htm)。实际兼容性以本机 Abaqus 2020 执行为准，不依赖较新文档新增参数。


## 本轮验收记录

首个 ANG18 算例已完成静力求解及 ODB 复核，详见 [验证结果](step07_validation_results.md)。最新生成器同时输出 `step07_verify_results.py`，可在求解结果已存在时独立复核，无需重新划网格或提交 Job。源 CAE 的 SHA256 在生成时记录，并在新执行开始/结束校验。
