# Step06 Phase 1：檩托主动孔与对侧派生孔

## Current shared PURLIN_BOLT preset

CARTESIAN; LINEAR / UNCOUPLED; components F1/F2/F3 (U1/U2/U3) only. D11=5.0E8 N/m, D22=2.0E8 N/m, D33=2.0E8 N/m. No rotational or off-diagonal stiffness, nonlinear, plasticity, damage, friction or failure behavior is defined.

All eight Support-Purlin and Support-Beam connectors share STEP06_CONNECTOR_SECTION_PURLIN_BOLT. Reports record parameter_source=TEMPORARY_PRESET and behavior_status=PRESET_FOR_WORKFLOW_VALIDATION; these are not final calibrated values. Local 1 remains the bolt axis, local 2 the projected slot major axis, and local 3 their cross product.

For an existing completed Step06-B CAE, run `<project>_step06_b_purlin_bolt_preset_update.py`. It first verifies all eight wire assignments and all sixteen KINEMATIC translation-only couplings, then changes only the shared Section's behavior options. It writes an independent preset report. It does not create or modify loads: the existing 20000 N local-component-1 Connector Force preload is preserved. No BC, contact, placement, RP, wire or orientation is changed. New-build scripts create the same preset directly.

The original no-behavior benchmark described below is historical and is superseded by this preset.


## Formal Bolt Connector Coupling Rule (2026-10-11)

All sixteen Step06-B bolt couplings (P01-P04, Support-Purlin and Support-Beam, both sides) use **KINEMATIC, translations only**: U1/U2/U3=ON; UR1/UR2/UR3=OFF. Names, RP positions, hole regions, wires and orientations are unchanged. This rule was confirmed by the user's real Abaqus SP_SC ANG18 Connector Force preload case; no Step04 placement correction is required.

For an existing eight-connector CAE, run `<project>_step06_b_kinematic_coupling_update.py`. It preflights all sixteen names and calls Coupling.setValues only. It neither recreates connectors nor edits Section, K1/K2/K3 (5.0e8/2.0e8/2.0e8 N/m), preload, contact, Step04 placement or Step05 constraints. An independent `_step06_b_coupling_update_report.json` records the update; historical creation reports are retained. The fresh-build scripts also create the new coupling rule, but should not be rerun over existing connectors.

Local stabilizing BCs belong to future Step07. No BC, Load, Step or Job is added by this update. The existing creation generator's uncalibrated Section behavior is unchanged in this coupling-only task; the migration preserves the user's existing constitutive settings and preload.


> 历史 Phase 1 说明。当前 v0.1 的中文 ROUND/SLOT schema、单文件夹 GUI、P01 开孔与共享 Part 保护见
> [Step06 Hole Setup](step06_hole_setup.md)。下文的仅 Plan 范围及固定两行英文表属于此前阶段。

本阶段只读取工程输入并生成可序列化 Plan。首个范围为 P01 的两条连接：

- `PS_TO_PURLIN`：PURLIN_SUPPORT → PURLIN_LOCAL 腹板。
- `PS_TO_BEAM`：PURLIN_SUPPORT → INCLINED_BEAM 对应上翼缘。

用户只输入檩托上的两个主动孔。檩条、斜梁的孔由主动孔轴与目标面求交派生，
不再接受用户填写对侧孔行、side A/B 或 XYZ 的旧输入模式。
本阶段没有 CutExtrude、Partition、RP、Coupling、Connector 实体、Abaqus Runtime、GUI 或 EXE。

## Bolt Hole Location Table

模板：`examples/step06/step06_bolt_hole_location.xlsx`。
仅含 `Bolt Hole Location Table` 工作表：第 1 行为表头，第 2、3 行是 P01 两孔。
项目编号、距根部、距端部及孔径留空，等待用户填写，不能直接当作有效工程输入。
没有示例工程尺寸，也没有预设螺栓刚度。黄色区域表示用户可填写或确认的内容。

| Excel 表头 | 内部字段 | 输入要求 |
|---|---|---|
| Project ID | project_id | 两行填写同一项目编号，与 assembly_summary 一致 |
| Connection Group | connection_group | 预填 P01，本阶段仅处理此组 |
| Component | component_role | 固定 PURLIN_SUPPORT |
| Hole ID | hole_id | 预填 PS_TO_PURLIN / PS_TO_BEAM |
| Connection Target | connection_target | 分别固定 PURLIN_LOCAL / INCLINED_BEAM |
| Angle Leg | leg | LONG_LEG / SHORT_LEG，按示意图预填，可核对 |
| Distance from Angle Corner (mm) | distance_from_angle_corner_mm | 用户填写，数值 > 0 |
| Distance from End (mm) | distance_from_end_mm | 用户填写，数值 > 0 |
| End Reference | end_reference | START / END；默认 START，用户确认 |
| Hole Diameter (mm) | hole_diameter_mm | 用户填写，数值 > 0 |
| Enabled | enabled | TRUE / FALSE；预填 TRUE |
| Remarks | note | 备注，可留空 |

表头顺序固定，工程字段只有这一套 schema。Reader 不接受公式、字符串数字、
NaN/Infinity、未知列或用户提供的对侧孔行。两行必须具有相同项目编号、不同合法孔 ID。
关闭 Enabled 只取消该孔的派生与连接意图，不豁免其输入/源孔几何有效性检查。
尚未填写的模板会明确报缺失输入，不将空值补成零。

P01 模板的关系为：

| Hole ID | 主动孔所在肢 | 自动目标 |
|---|---|---|
| PS_TO_PURLIN | LONG_LEG | 同 connection_group 的 PURLIN_LOCAL |
| PS_TO_BEAM | SHORT_LEG | 唯一 INCLINED_BEAM |

用户不填写 target_instance。解析以 summary 的角色与 connection_group 为准，
不依赖实例名称尾缀猜测。梁没有 P01 分组时允许按唯一角色解析；多根梁则拒绝歧义。
两条输入必须分别位于两个肢面。目标接触面的几何一致性尚待 Runtime 验证。

## 根部与 Part-local 坐标

用户于本轮确认：距离以**角钢外侧两平面的理论交线 (0,0)** 为零点，
与现有 Step02/Step04 装配根部基准一致。
不是内侧理论交线 (t,t)，也不是自由边、圆角切点或圆弧边界。
内圆角 Ri 不改变距离零点。

本基线 `scripts/abaqus_build_parts.py::_draw_angle_profile` 的几何契约为：

- a 肢沿 Part-local +X，b 肢沿 +Y；局部长度沿挤出方向 +Z。
- START 对应 z=0，END 对应 z=L；与 Assembly 的视觉左右无关。
- 长、短肢由实际 a/b 尺寸识别；等肢不能唯一解释 LONG_LEG/SHORT_LEG，本阶段拒绝。
- 本阶段要求檩托为 SOLID ANGLE，目标为 C_CHANNEL SHELL。

将 mm 转为 m，令距根部 d、距端部 e、长度 L、厚度 t：

```text
z = e         (START)
z = L - e     (END)

沿 +X 的肢：local_center_m = (d, t/2, z)，local_axis = (0,1,0)
沿 +Y 的肢：local_center_m = (t/2, d, z)，local_axis = (1,0,0)
```

这里孔中心取肢厚度中面上的轴线代表点，轴为无向直线，不表示未来切孔深度或进刀方向。
不从截图像素推算尺寸。

几何 preflight 要求整个孔圆在直肢有效区域和长度端部以内：
`d-r > t+Ri`、`d+r < 对应肢长度`、`min(z,L-z) > r`，并使用 1e-9 m 数值容差。
这样排除根部圆角/另一肢厚度区域及自由边、端部相交；输入不自动调整。
这只是几何包含检查，不代表满足螺栓连接设计规范的最小边距要求。

## Plan 数据与派生链路

`hole_inputs.py` 读取工程输入为 `HoleLocationRow`；`hole_plan.py` 结合标准化组件
和 assembly_summary 构建 `DrivingHoleSpec`、`DerivedHoleSpec`。

DrivingHoleSpec 记录：稳定 ID、项目/组、源角色/实例/Part、目标角色、肢、两种距离（m）、
端部、孔径（m）、自动计算的 Part-local 中心/轴、启用状态、校验状态、Excel 行号及共享 Part 信息。

DerivedHoleSpec 记录：稳定 ID、source_driving_hole_id、项目/组、目标角色/实例/Part、
`AXIS_SURFACE_INTERSECTION` 方法、源中心/轴的全局值（可空）、目标局部中心/轴（本阶段空）、
孔径、目标面语义、姿态/几何校验状态及共享 Part 信息。
所有带长度的坐标和尺寸统一为 m，方向向量无量纲。

后续派生流程：

```text
source Part-local center/axis
→ 经核实的 source placement → Assembly global center/axis
→ 与目标语义面求交 → global target center
→ 经核实的 target placement 逆变换 → target Part-local center/axis
```

PS_TO_PURLIN 的目标面语义为 `PURLIN_LOCAL_WEB`；
PS_TO_BEAM 为 `INCLINED_BEAM_TOP_FLANGE`。
这些是目标意图，不是已解析的 Abaqus Face。
本阶段不执行面求交：目标坐标始终为 `None`，状态为 `TARGET_SURFACE_PENDING_RUNTIME`。
未来必须核实面身份、法向、厚度偏置、交点唯一性及孔域在目标面内，不能直接复制源 XYZ。

复用 `analysis_geometry.placement_candidates` 检查旧 summary 的平移/旋转顺序。
仅当所有候选变换等价时输出源中心/轴的全局预测值，标记
`SUMMARY_TRANSFORM_UNAMBIGUOUS_RUNTIME_UNVERIFIED`；若不唯一则保留 `None` 和
`POSE_PENDING_RUNTIME`。不静默挑选第一种变换。

两行均启用且通过 preflight 时：DrivingHoleSpec ×2、DerivedHoleSpec ×2。
停用行记录在 `disabled_hole_ids`，不产生派生孔或连接意图。

稳定语义 ID 示例：

```text
STEP06_DRIVING_P01_PS_TO_PURLIN
STEP06_DRIVING_P01_PS_TO_BEAM
STEP06_DERIVED_P01_PURLIN_FROM_SUPPORT
STEP06_DERIVED_P01_BEAM_FROM_SUPPORT
STEP06_CONNECTOR_P01_PS_TO_PURLIN
STEP06_CONNECTOR_P01_PS_TO_BEAM
```

`connector_plan.py` 仅记录主动/派生孔的一对一关联及未来 `PURLIN_BOLT` 属性族。
`HOOP_BOLT` 仅保留名称，没有本阶段输入或执行支持；`behavior_status=NOT_CALIBRATED`，无刚度数值。

## Shared Part 与接口边界

对源檩托、目标檩条及目标斜梁，分别统计 summary 全部实例中引用同一 Part 的实例。
多实例共享时记录 `shared_part=True`、`requires_instance_isolation=True` 及所有实例名。
这是一项保守的后续处理要求；本轮不复制 Part、不重建 Instance、不改变 Assembly。
同一根梁仅有一个实例、但承接多个连接位置时，不混淆为“多实例共享 Part”。

`load_hole_plan(components_path, summary_path, hole_input_path)` 只使用稳定数据文件。
组件读取复用 `workbook.export_abaqus_json(selection="complete")`，保留派生 PURLIN_LOCAL 能力，
中间标准化 JSON 放在临时目录；核对组件 code/Part 和 summary 长度。
本阶段不需要 coordinate.xlsx，不解析 assembly_frame.py 或 analysis_setup.py。
没有修改 Step04、Step05 或其运行时模块。

## 验证

在 Step06 worktree 内：

```powershell
$env:PYTHONPATH='src'
.\.venv_step06_build\Scripts\python.exe -m unittest discover -s tests -p 'test_step06_*.py' -v
```

测试包括工程表读取、空模板拒绝、非法字段/旧 schema、孔配对、根部与端部坐标、
圆角/自由边/端部 preflight、同组解析、共享 Part、变换歧义、稳定 ID、序列化及未标定属性。
测试中的数值尺寸仅为合成 fixture，不写入用户模板，也不作为真实工程参数。
