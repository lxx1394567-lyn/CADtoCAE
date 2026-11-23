# BatchRunner V4 技术审查（2026-10-20）

开发仅在 `CADtoCAE-BatchRunner / feature/batch-runner`，Step07 工作区只读检查。未修改建模算法。

## 确认的接口

来源：`../CADtoCAE-Step07-Development/src/cadtocae/step07_inplace.py`、`step07_inplace_runtime.py`、`step07_load_runtime.py`、`step07_runtime.py`、`step07_quality_runtime.py`；与 `../CADtoCAE-EXE-Testing/20261019` 实际生成脚本核对。

|执行序号|功能|准确文件后缀|实际运行输入|
|---|---|---|---|
|1|Part|`_create_parts_in_cae.py`|COMPONENTS_JSON 内嵌数据|
|2|Assembly|`_assembly_frame.py`|ASSEMBLY_DATA 内嵌数据、阶段1检查点|
|3|Analysis|`_analysis_setup.py`|PLAN 内嵌数据、阶段2检查点|
|4|Hole|`_step06_hole_setup.py`|Hole PLAN/声明的运行输入、阶段3检查点|
|5|Tie|`_step07_01_tie_setup.py`|INPLACE_PLAN、阶段4检查点及本轮Hole报告|
|6|Step|`_step07_02_step_setup.py`|INPLACE_PLAN、阶段5检查点、本轮Hole报告|
|7|BC|`_step07_03_boundary_setup.py`|INPLACE_PLAN、阶段6检查点、本轮Hole报告|
|8|Mesh|`_step07_04_mesh_setup.py`|INPLACE_PLAN、阶段7检查点、本轮Hole报告|
|9|Load|`_step07_05_load_setup.py`|INPLACE_PLAN、阶段8检查点、本轮Hole报告、指定Load JSON|

所有文件名前面是完整项目编号，同一项目目录成组。示例 Load JSON 是 `DP_ANG14_FA03521S-T0104-02_J13_step07_loads.json`，路径和 SHA-256 由实际 INPLACE_PLAN 指定，不猜测其他项目或最近文件。JSON 项目身份、内容哈希必须匹配；输入变化但 PY 内嵌哈希未更新时要求重新生成 Load PY。Excel 由 Step07 生成器消费，BatchRunner 不会假装直接读取工作簿或自动更改生成器参数。

Step07 当前正式接口 `step07-inplace-1 / CURRENT_MDB_IN_PLACE` 不打开、关闭或保存 CAE，不启动子进程。包装器只修改运行副本的日志/输入路径并捕获 `u7_run` 返回报告；建模函数原样保留。日志、快照、检查点全部进入 `.batchrunner`。

旧 `step07-chain-2` pipeline 和早期 `_step07_01_step.py` 不作为当前五个子阶段识别；它们的阶段语义、打开/保存行为不同，须由当前生成器重新生成。`_step07_06_inp_export.py` 不运行。

## 计算步和对象依赖

本项目原 Analysis 脚本没有 StaticStep 调用，不创建计算步。Step07-02 要求严格序列 Initial → STEP07_PRELOAD → STEP07_LOADING；若已有步骤，读取并校验全部参数，不删除、不静默重命名或覆盖。发生 STEP_SEQUENCE_MISMATCH/STEP_PARAMETER_MISMATCH 时保留上游检查点并阻止后续阶段；不添加未经授权的自动清理。

Tie 检查当前装配几何、旧 Connector 对象、接触区域及连通性，复制四个 Hoop Part 后按实例隔离分区。BC 检查 Tie、计算步、几何区域与 RP；Mesh 检查 BC、已有约束与网格质量；Load 检查已网格化的局部檩条、作用步、方向、面积、区域、荷载参数及生成时JSON哈希。

因此最终验证不能沿用旧规则要求 Hoop 实例继续指向原共享 Part，应根据本次 Tie 报告的 isolated_parts 验证。最终检查依据当前有哈希保护的报告，对 Tie 名称/区域、Step 参数、BC/RP/传播状态、Mesh 数量/类型、Load 作用步/方向/大小/区域进行独立重新打开检查。

## 移除旧 Connector 的范围

扫描后缀移除两种旧 Connector 别名；移除其生成来源/必需计划及特殊Hole报告绑定；最终验证移除 Connector 数量要求，改为确认 Step07 中不存在旧 Connector 对象。五阶段记录不作为九阶段完成或迁移候选。旧源文件和用户 CAE 不删除。

指纹增加 `hole-step07-nine-v1` 工作流标识；阶段、脚本、输入、适配器/验证器、有效上游检查点均参与哈希。旧版记录首次保守失效，防止第五阶段 Connector 被当成 Tie。新版本内部未变的阶段仍可复用。

## 扫描目录与实际限制

20261019 的 `过程文件` 内有同名历史脚本。该内部目录、Step07_Logs、CAE_Results、.batchrunner、build、dist 不作为项目源码根扫描。真实项目源目录中重复项目仍报告冲突；不会按修改时间选版本。

网格实现 `q4_diagnostics` 明确规定：严重问题 FAILED，未解决警告 REVIEW_REQUIRED，无自动豁免。本项目历史报告已有 REVIEW_REQUIRED。BatchRunner 保留该判定，保存内部 review_only.cae 诊断模型，不将其作为有效检查点、不执行 Load、不更新完整交付。该限制必须在真实验证报告中说明，不能声称九阶段验收通过。

## 修改模块

scanner、dependencies、step07_adapter、executor、cae_worker、preflight/state/runner、delivery/step07_verify/delivery_worker、publication/migration、GUI/CLI、构建脚本与回归测试。复用现有串行执行、安全发布、历史记录与 SHA-256 机制。
