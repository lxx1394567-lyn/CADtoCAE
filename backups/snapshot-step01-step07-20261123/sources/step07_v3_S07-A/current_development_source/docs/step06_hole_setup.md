# CADtoCAE Step06-A v0.2 — Hole Setup

范围：PURLIN_SUPPORT 主动孔 + PURLIN_LOCAL WEB 派生孔 + INCLINED_BEAM TOP FLANGE 派生孔。
P01～P04 全部处理。本版不执行 RP、Coupling、Wire、Connector 或 Step05 integrity check。
不自动打开/保存 CAE，不自动最终重划分网格。主动孔、局部檩条和斜梁派生孔均已由用户在真实 Abaqus/CAE 中验证。
HOOP 圆孔作为新增最后阶段；这三类孔的 runtime 文件保持不变。

## 每项目孔位表工作流

1. Select Folder → Scan Projects。
2. Generate Hole Tables：为每个项目创建 `<project_id>_螺栓孔定位表.xlsx`。
3. 用户填写黄色尺寸单元格，再次 Scan Projects。
4. READY 后，Generate Selected / Generate All Ready 生成同目录的 Plan JSON 和 Abaqus script。
5. 从干净的 Step05 CAE 手动运行新脚本；最后执行公共 HOOP Part 圆孔 Cut。

状态：MISSING_TABLE 为缺少项目表；NEEDS_INPUT 为必填尺寸缺失；READY 为输入完整；
GENERATED 表示输出对已存在。非法尺寸、schema 或 Part 映射为 NEEDS_REVIEW。
已有输出不会掩盖缺表或待填状态，GUI 同时显示 Input 和 Generation。
Generate Hole Tables 遇到已有文件始终显示 `Existing hole table preserved.`，不覆盖、不补写。
旧 `Step06_螺栓孔定位表_中文版.xlsx` 仅提示 LEGACY_AGGREGATE_TABLE，不再作为默认输入。

必需输入仍是同目录 `<project_id>_components.xlsx` 和 `<project_id>_assembly_summary.json`。
孔位表以文件名前缀为项目身份唯一主来源，匹配同名前缀的 components/summary。
严格校验两个可见 Sheet 及 header schema；Office core/custom properties 和 defined names 不参与身份判定。
新表另带隐藏 `_STEP06_META`，包含 schema_version=step06-project-hole-table-v1、project_id。
隐藏 metadata 缺失时警告 `Workbook metadata missing; filename identity used.`，仍读取原可见数据。
隐藏 project_id 明确冲突时阻塞：`Workbook metadata conflicts with filename identity`。
文件名前缀无法匹配扫描项目时显示 NEEDS_REVIEW；不会静默忽略孤立孔位表。
不解析 assembly_frame.py / analysis_setup.py；不读取 Assembly 视觉方向推测孔位。
分发 EXE 时保留整个 `dist/CADtoCAE_Step06_HoleSetup` 目录和 `_internal`。

### 檩托孔位

字段：构件、孔位编号、连接目标、所在角钢肢、距角钢直角根部 (mm)、距端部 (mm)、
端部基准、孔型、孔宽/直径 (mm)、槽孔总长 (mm)、槽孔长轴方向、启用、备注。
项目编号和连接组已从用户输入移除；内部将两条标准定义绑定 P01，沿用已验证的共享 Part 继承规则。
自动填写两条 PS_TO_PURLIN / PS_TO_BEAM 定义及枚举，工程尺寸留空；不自动迁移旧总表。
当前支持一个 unique PURLIN_SUPPORT Part，多个不同檩托 Part 会明确要求复核。
每个实际连接组须有同组 PURLIN_LOCAL 与唯一 INCLINED_BEAM，两条檩托孔均须启用。

### 抱箍孔位与 Plan

字段：构件、适用Part、孔位编号、端部基准、距端部 (mm)、距宽边 (mm)、孔型、孔径 (mm)、启用、备注。
按 summary 中 unique HOOP Part 自动生成 HOOP_LEFT / HOOP_RIGHT 两行；多个 Part 分别生成两行。
适用Part、孔位编号、端部基准等自动字段锁定，用户填写距端部、距宽边、孔径。
50/40/16 mm 仅是用户提供的当前工程示例，不作为跨项目默认值。禁用的抱箍孔允许尺寸留空。

坐标依据当前 main 的 Step02 修正轮廓：`scripts/make_cae_runner.py` 中
`_hoop_band_dimensions` / `_hoop_band_profile_geometry`（main a0092c0）。
Step06 的旧基线含旧 offset 轮廓，不能拿旧实现的负 Y 厚度当成当前 Part 约定；本轮未修改 Step02。

- X：左/右端；Y：圆弧凸起及耳板厚度方向；Z：带宽挤出方向，0～W。
- Ri=D/2，Ro=Ri+T；左端 X=−Ro−L，右端 X=Ro+R。
- 耳板内表面 Y=0、材料在正 Y；孔中心 Y=T/2，孔轴为局部 +Y。
- 左孔 X=左端+距端部，右孔 X=右端−距端部；Z=距宽边（从 Z=0 量取）。
- 圆角切点绝对 X 为 `sqrt(Ri*(Ri+2*(RF+T)))`；从端部到切点才是平直耳板区。
- 孔的整个圆形轮廓必须严格位于平直区和带宽内；边界接触、跨入过渡圆角/圆弧均拒绝，不移动孔。

`hoop_hole_plan.py` 输出 HoopDrivingHoleSpec：local_center/axis、米制定位尺寸、shared_part_info、
VALIDATED_INPUT 和 CUT_PENDING_RUNTIME_PREFLIGHT。Plan 中 `hoop_hole_plan.runtime_enabled=true`。
组件几何由 components 读取并精确匹配 Part；不要求用户重复填写 D/W/T/L/R/RF。
公共 Part 的两条定义适用于全部引用实例，记录未来 MODIFY_SHARED_PART_ONCE 策略；只修改公共 Part 一次。
历史旧轮廓 CAE 的 HOOP 不适用上述正 Y 约定，runtime 会拒绝负 Y 旧轮廓、X/Z 范围或耳板厚度不符的 Part。

### 已验证的 Step06-A 孔

| 主动孔 | ANG18 已确认尺寸 | 距根部 / START 端 | 槽长方向 | 派生目标 |
|---|---|---|---|---|
| PS_TO_PURLIN | SLOT 12×40 mm | 60 / 25 mm | 沿长肢 | PURLIN_LOCAL WEB |
| PS_TO_BEAM | SLOT 12×25 mm | 21 / 25 mm | 沿檩托长度 | INCLINED_BEAM TOP FLANGE |

ROUND 使用直径；SLOT 使用宽度、端到端总长和长轴。总长不小于宽度，不从备注猜测尺寸。
根部仍为外侧两平面理论交线 (0,0)，Ri 不改变零点；START z=0，END z=L。
Excel 原文件保持不变。目标继承源孔的类型、宽度、总长和全局长轴方向。

## 姿态、求交和共享检查

Runtime 唯一位姿来源是 assembly_summary 的 placement：执行 PRE_TRANSLATION_ROTATIONS → TRANSLATION → POST_TRANSLATION_ROTATIONS。
兼容 step04-instance-plan-v1：连续的原点旋转为 pre；首次非零全局轴心（阈值 1e-12 m）及后续旋转均为 post。
这与 Step04 `_instance` 的 orientation → translate → roll → post_rotation 调用顺序一致。
每步完整处理 axis_point、axis_direction、angle_deg。向量只旋转并归一化，不叠加轴心或最终平移。
逆点变换先逆序撤销 post，再减 translation，最后逆序撤销 pre；逆向量只逆序撤销 post/pre。
四个统一 helper 位于 hole_transforms.py；Step06-A 不调用 fit_pose，不读取 Instance 顶点/面排序反求位姿。

每个实例须有独立的 local/global 装配锚点并通过 1e-6 m 校验。
优先使用 summary 中显式 transform_anchors 或 local_anchor/global_anchor。
旧格式支持从 assembly_points 的 G_global、F、P1～P4 和 Step04 已定义的截面参考规则建立锚点：
Beam 局部 (0,h/2,0) 对应 G_global；檩托/局部檩条使用长度中点和 Step04 截面/间距偏移。
不从同一 placement 自造 expected_global 来通过检查。
缺锚点时报 SUMMARY_ANCHOR_MISSING，不一致时报 SUMMARY_TRANSFORM_INCONSISTENT，所有修改前停止。
生成时把诊断写入 Plan 的 summary_transform_validation；允许生成诊断脚本，但 GUI 明确警告其不能执行开孔。
Runtime report 的 transform_checks 记录每实例的 expected/actual global、误差及往返误差。
保持既有 summary 和 Step04 schema 不变；Beam 校验 G_global/F/C/E，Brace 回归校验 B/C、D/E。

源局部孔中心/轴/长轴 → summary 源实例变换 → 全局轴线 → 目标语义平面交点 → summary 逆目标变换。
不复制源 Part-local XYZ 到目标。只支持现有 Step02 C-channel 约定：WEB x=0，TOP FLANGE y=h。
已知截面用于界定语义平面，实际目标面、法向、几何范围和面积用于核实。

四组 PURLIN_LOCAL 结果在 1e-6 m 位置/尺寸容差和 1e-6 方向余弦容差内比较；一致才执行
`MODIFY_SHARED_PART_ONCE`。不同孔型触发 `PART_ISOLATION_REQUIRED`，当前不自动隔离。
公共 Part 的实际全部引用必须与已验证实例集吻合，且全部 dependent。
Beam 的四个孔独立命名并检查轮廓包络不得重叠。

## 预检与执行

所有目标几何和全部节点完成预检之后才允许任何删网格、datum、sketch 或开孔操作。
目标必须为原生 SHELL C_CHANNEL；检查截面尺寸、长度、面积、目标面语义、孔轴与法向一致、
长轴在面内、完整槽孔轮廓位于一个矩形目标面内。越界/跨分割边界/非唯一目标直接停止，不调整孔位。
当前不支持槽孔跨越多个已有分割面，也不开发通用任意 Face-ray 框架。

执行顺序：

1. 公共 PURLIN_SUPPORT 两个主动孔（或复用已验证孔）。
2. 公共 PURLIN_LOCAL 一个派生孔。
3. INCLINED_BEAM P01、P02、P03、P04 四个派生孔。

目标 Part 有 nodes/elements 时使用已验证的 `part.deleteMesh()`，仅在所有预检后调用，
删除后检查无残余网格。报告 `mesh_removed_parts`、`remesh_required_parts`、删除前节点/单元数。
不重建/旋转/平移实例，不修改其他 Parts。

主动孔沿用已验证 CutExtrude。壳体派生孔使用 `PartitionFaceBySketch(faces=(target_face,), ...)`
仅在指定面绘制闭合槽孔，检查分割内部面积后用 `RemoveFaces(faceList=(inside,), ...)` 移除槽孔内部。
不会对整个 C-channel 作 through-all 切除。每次操作核对五类表面面积，非目标表面面积必须保持不变。
槽孔为两条直线和两个半圆，草图长轴由实际局部长轴投影到 sketch U/V 得到。

稳定特征名：

- STEP06_HOLE_PS_TO_PURLIN
- STEP06_HOLE_PS_TO_BEAM
- STEP06_HOLE_PURLIN_FROM_SUPPORT
- STEP06_HOLE_BEAM_P01_FROM_SUPPORT ～ STEP06_HOLE_BEAM_P04_FROM_SUPPORT

## 从当前主动孔模型继续

保留现有成功的 `<project>_step06_hole_report.json` 在项目目录。
Runtime 核对报告中的源孔参数、特征名、Part 及实际剩余体积/范围后复用，不重复切主动孔。
也支持从尚未执行 Step06 的原始模型开始，先完成全部派生预检再执行主动孔。
既有派生孔或部分派生特征不自动重试；发生 mutation 错误需检查部分模型，重新打开派生前模型。
没有自动回滚几何或自动保存。报告保存已创建特征、部分修改和错误。

## 报告与验收

`purlin_local`：P01～P04 局部中心、轴、长轴、共享孔型比较、执行策略、特征名。
`inclined_beam`：四组源实例、源全局中心、全局孔轴/长轴、交点、Beam 局部中心/轴/长轴、特征名。
`support_validation` 保留主动孔成功证据；`support.status=REUSED_VERIFIED` 表示复用。
`created_holes` 为本次新建孔数：新模型为 7，已有主动孔时为 5；实例中会显示共 16 个孔。
人工检查四组对应孔同轴、槽长方向正确、斜梁孔全在上翼缘，未误切 web/lower flange/lip。

## 开发验证

```powershell
$env:PYTHONPATH='src'
.\.venv_step06_build\Scripts\python.exe -m unittest discover -s tests -p 'test_step06_*.py' -v
.\scripts\build_step06_exe.ps1
```

使用独立 `.venv_step06_build`，不改系统 Python 或 Step05 环境。
脚本自包含，不在 Abaqus 读取 Excel，生成时执行兼容 lint；另以 Abaqus Python 2.7 编译检查。

API 参考：[PartitionFaceBySketch](https://ceae-server.colorado.edu/v2016/books/ker/pt01ch20pyo01.html)、
[RemoveFaces](https://ceae-server.colorado.edu/v2016/books/ker/pt01ch37pyo02.html)。
文档和模拟测试不等于真实 Abaqus 内核验收。生成 EXE/真实项目脚本后停止，不 commit、push 或 PR。

## HOOP 圆孔执行

独立 `hoop_hole_runtime.py` 包装已有 Step06-A：先验证全部 HOOP 输入、共享依赖、
SOLID、X/Z 范围、平直耳板圆形轮廓、Y=0/T 两侧平面和法向；再运行原 Step06-A；最后执行 HOOP。
每个 unique Part 在预检通过后调用无参数 deleteMesh()（如有网格），不自动 remesh。
Plan 的局部孔中心直接用于 sketch 原点投影，不交换 A/B 实例的左右孔，不重新计算用户定位尺寸。

在 Y=0、外法向 −Y 的耳板面上用 CircleByCenterPerimeter 绘制圆，CutExtrude depth=T，
方向与已有 SOLID 檩托开孔方式一致。两个独立 Feature：STEP06_HOLE_HOOP_LEFT / STEP06_HOLE_HOOP_RIGHT。
辅助 Sketch/Datum 使用 STEP06_HOOP_ 前缀，每次 Cut 后重新查找 native Face。
逐孔及整 Part 检查体积差：πd²T/4，误差不超过 max(理论值×1e-4, 1e-12 m³)。

assembly.regenerate() 后复核 cells、累计体积差和每孔圆柱壁：四个避开常见 seam 的圆周方向、三个厚度位置，
共 12 个探针，法向指向孔轴；独立圆柱面的面积合计须等于 2πrT。
同时核对每个 dependent instance 的 Part 引用。Feature 名称/抑制状态仅作辅助证据，
缺失或异常而几何通过时记录 NOT_CONFIRMED_AFTER_REGENERATE 和 warning，不单独判失败。
report 记录 cut_geometry_status、volume_validation、assembly_inheritance_status、feature_repository_status。
report.hoop_validation 含每 Part、每孔、网格、体积和继承证据；单 Part 时也提供顶层 Part 摘要。
组合 created_holes 包含原有 7 次标准/派生操作和新增 2 次 HOOP 操作（ANG18 共 9）。
失败报告明确记录已修改及已创建的对象，不自动重试或回滚；已有 HOOP Feature 时拒绝重复执行。
本阶段不修改实例 placement/rotation 或 Step05 Tie，不派生 BRACE/COLUMN 孔。
实际 Abaqus 几何内核与孔方向仍由用户从干净 Step05 CAE 人工验收。

### Step06 desktop release 0.2.1

GUI 标题、桌面生成的 Plan、脚本及新执行报告统一记录
`step06_version = generator_version = 0.2.1`。
Generate Selected / Generate All Ready 生成 Hole Setup；存在匹配的成功
Step06-A report 时同时生成四组 Support–Purlin Connector 脚本；存在成功的
Support–Purlin report 时另生成四组 Support–Beam 脚本。各脚本仍按前置模型状态分别运行。
共享 PURLIN_BOLT 为 CARTESIAN / LINEAR / UNCOUPLED，刚度为
5.0e8 / 2.0e8 / 2.0e8 N/m；16 个 Bolt Coupling 为 KINEMATIC，
U1/U2/U3 开、UR1/UR2/UR3 关。20000 N、local-1 仅作为 preload 目标记录，
生成器不创建载荷，保留 CAE 中已有 preload。

构建命令：`.venv_step06_build` 环境运行
`scripts/build_step06_exe.ps1 -SmokeFolder <隔离的完整 ANG18 测试目录>`。
先在 `build/step06-release-*` 全新构建并执行 GUI smoke，通过后替换
`dist/CADtoCAE_Step06_HoleSetup/CADtoCAE_Step06_HoleSetup.exe`。
若 EXE 正在运行则停止替换并提示关闭重试；旧包保留在本次 build 目录供恢复。

### Step06 desktop integration 0.2.2

修复 0.2.1 把运行报告当作脚本生成前提的问题。READY 工程的 Generate Selected /
Generate All Ready 始终同时输出：

- `<project_id>_step06_plan.json`
- `<project_id>_step06_hole_setup.py`
- `<project_id>_step06_connector_plan.json`
- `<project_id>_step06_connector_setup.py`

独立 Connector Plan 保存 Hole Plan、报告位置和两族执行契约；精确派生孔位置在 CAE
运行时从匹配的成功 Step06-A report 读取。无需先运行 CAE 再返回 GUI 生成第二份脚本。
执行顺序：Step02 → Step04 → Step05 → Hole Setup → Connector Setup。
Connector Setup 不开孔。缺少成功的 A 报告或实际孔区域时失败，提示 `STEP06_A_REQUIRED`。
同一份孔 Plan 仅版本号变化时可复用原 A 报告；工程输入变化必须重新完成 A。

两族为 P01–P04 Support↔Purlin、P01–P04 Support↔Beam；先完成八组区域和方向校验，
再调用既有执行器。16 RP、16 KINEMATIC U123 Coupling、8 Wire/Connector，共享一个
CARTESIAN LINEAR UNCOUPLED PURLIN_BOLT Section（5e8、2e8、2e8 N/m）。
参数为 TEMPORARY_PRESET / PRESET_FOR_WORKFLOW_VALIDATION。
按用户确认不创建 preload，仅记录 20000 N / local-1，保留已有载荷。
已有 Step05 约束必须存在并保持；重复 Step06 Bolt 对象会被拒绝。
第二族失败时外层事务尝试回滚两族新增对象。

### Model resolution correction 0.2.3

Step06-B 的两族 preflight 和独立 Coupling／Section 更新器统一调用
`resolve_step06_model(mdb, project_id)`。只接受非空字符串及与 project_id
精确相等的 Model key；Abaqus 2020 使用匹配到的 Repository 原生 key 索引，
避免 JSON Unicode key 的 API 类型问题。Copy、origin、Model-1 不参与选择。
不存在正式模型时报告 TARGET_MODEL_NOT_FOUND 和 Available Models，绝不回退。
实例、孔区域、重复对象分别报告 INSTANCE_MISSING、HOLE_REGION_MISSING、
EXISTING_STEP06_B_OBJECT；不再用泛化的 Step06-A 错误包装 Model resolution。
Hole Runtime、RP／region／orientation 算法、U123 KINEMATIC、Section 刚度及
preload metadata 保持不变。

## Release 0.2.4: SP_SC Connector capability

Support-Purlin and Support-Beam P01-P04 now use assembly_summary.structure_type=SP_SC rather than an ANG18 project-name restriction. Both profiles inherit successful Step06-A dimensions; source/target dimensions and axes must agree. SLOT length equal to width is treated as a circular-equivalent hole (12 unique probes, perimeter pi*d). Existing elongated slots retain their resolver.

KINEMATIC U1/U2/U3 only, shared CARTESIAN PURLIN_BOLT stiffness (5e8, 2e8, 2e8 N/m), orientations, and no automatic preload creation remain unchanged. Run the regenerated connector script after successful Step06-A in a model without existing Step06-B objects. This release does not add HOOP-Brace integration.
