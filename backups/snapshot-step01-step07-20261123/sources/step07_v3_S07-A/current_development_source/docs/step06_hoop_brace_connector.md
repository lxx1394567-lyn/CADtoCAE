# SP_SC ANG18 — HOOP A ↔ BRACE Connector

本阶段为独立增量脚本。前提是当前 CAE 已完成 Step05、Step06-A 和两族共八条
Support/Purlin、Support/Beam Connector。无需重跑这些脚本。

运行 `<project_id>_step06_hoop_brace_connector_setup.py`，输出独立
`<project_id>_step06_hoop_brace_connector_report.json`。
生成命令：

```
.venv_step06_build/Scripts/python.exe scripts/step06_generate_hoop_brace_connector.py --folder <工程目录> --project <项目编号>
```

## 明确的 ANG18 工程约定

- Front：HOOP_01_A / HOOP_LEFT ↔ BRACE_FRONT_01。
- Rear：HOOP_01_A / HOOP_RIGHT ↔ BRACE_REAR_01。
- A/B 等距时不做最近距离推断。Plan 记录两个 half 字段为 A。
- Hoop RP 位于 φ16 孔中心；Brace RP = Hoop RP + (0, −0.005, 0) m。
- Hoop 使用真实圆孔内壁；Brace 使用 Step05 已切分的 Part-local Z=0–0.050 m
  C_CHANNEL 腹板（X=0），以顶点、面法向、变换后几何和面积验证完整区域。
- 不要求 Brace RP 位于 shell midsurface；不在 Brace 上开孔或再次 Partition。
- 两侧 KINEMATIC U123 开、UR123 关。
- local-1 为 Hoop→Brace，即 −global Y；local-2 为 Brace 轴向投影；local-3 为叉积。
- 独立 STEP06_CONNECTOR_SECTION_HOOP_BOLT，CARTESIAN / LINEAR / UNCOUPLED。
  D11=5e8、D22=D33=2e8 N/m；TEMPORARY_PRESET / PRESET_FOR_WORKFLOW_VALIDATION。
- 不创建 preload、Boundary、Load 或 Job。

两组全部 preflight 后才创建对象。预计新增 4 RP、4 Coupling、2 Wire/Connector、
2 Orientation、1 Section。执行失败后尝试回滚本轮新对象；报告回滚失败时应恢复运行前 CAE。
已经成功执行后不要重复运行，同名对象会触发重复检查。

本轮不改变 GUI/EXE 入口；使用独立脚本等待真实模型验收，不涉及 HOOP↔COLUMN、SP_DC 或 DP。

## 验证

`tests/test_step06_hoop_brace_plan.py` / `tests/test_step06_hoop_brace_runtime.py`。
`tests/abaqus_hoop_brace_probe.py` 在 outputs/step06_hoop_brace 中使用测试 runtime，
仅创建未保存的合成模型。覆盖两条圆孔壁/腹板连接、Rear preflight 失败零修改、
创建后回滚以及原八条 Connector 与 Step05 的保留。
