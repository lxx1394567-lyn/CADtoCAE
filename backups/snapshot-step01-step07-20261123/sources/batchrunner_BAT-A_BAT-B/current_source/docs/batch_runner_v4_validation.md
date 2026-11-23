# BatchRunner V4 验证记录（2026-10-20）

## 结论与未完成验收

九阶段调度、接口绑定、GUI、开发版 EXE 已实现。真实项目 Part 至 BC 共七阶段完成并独立验证；Mesh 实际执行但返回 REVIEW_REQUIRED，Load 正确 BLOCKED。**没有完成九阶段真实全通过验收，没有生成或宣称已验证的新版 final.cae。** 原建模算法未修改，未豁免原 Step07 网格警告。

真实项目根目录：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20261019`。

项目：`DP_ANG14_FA03521S-T0104-02`，key `84c8cdd88b5be1673ab4`。

## 技术与 Mock 验证

技术审查详见 `batch_runner_v4_audit.md`。先验证 Mock，再执行真实 Abaqus。

新增测试覆盖九阶段顺序、未修改复用、逐阶段 PY 变更（相同大小/保留时间戳）、前置检查点丢失、失败阻断、部分阶段/中间缺失、九项目独立失效、旧 Connector 排除与旧记录不复用、内部历史目录排除、Step07 包装器仅改配置、Load JSON 缺失/身份/哈希、REVIEW_REQUIRED 不交付和不放行 Load。已有发布测试已更新为九阶段，仍验证重复发布固定文件、Windows 占用、异常恢复、未验证候选不覆盖、部分成果保护与九项目独立交付。

全仓测试：**249 项，248 通过，1 跳过**（原有 PDF 样本缺失）。日志 `outputs/v40_full_tests_final.log`。早期回归日志中的五阶段断言已按新阶段数更新并复测，不应将早期失败日志视为最终测试结果。

## 实际运行

1. `20261020-074934-11882ced`：从 Part 开始，Hole 后直接 Tie，旧 Connector 从未执行。BC 保存后的检查暴露 Abaqus 2020 API 名称差异。
2. 仅修复 BatchRunner 验证器：Encastre 在 Abaqus 2020 为 TypeBC，通过 boundaryConditionStates.typeName 验证 ENCASTRE；DisplacementBC 的自由度值读取计算步状态。原脚本保持不变。
3. `20261020-075207-11296143`：前七阶段执行/复用成功，Mesh 实际生成但原报告 REVIEW_REQUIRED，Load 阻断。
4. `20261020-075410-4ba568e8`：最终接口/验证器指纹建立后，使用 `--through 7` 完成独立阶段性交付。
5. `20261020-075736-a220d394`：默认九阶段完整尝试，前七步 REUSED；Mesh 状态明确 REVIEW_REQUIRED；Load BLOCKED；不发布新完整模型。内部保存 `step8/review_only.cae`（3,588,096 字节），不是有效续跑检查点。

最终网格报告：

`.batchrunner/20261020-075736-a220d394/84c8cdd88b5be1673ab4/step8/runtime_report.json`

报告包含 46,846 个装配节点、24,348 个装配单元、56 个质量警告单元。以下 Part 仍有 analysis/aspect 警告：BRACE_REAR、INCLINED_BEAM、STEP07_ISOLATED_HOOP_01_A、STEP07_ISOLATED_HOOP_01_B、STEP07_ISOLATED_HOOP_02_B。原 `q4_diagnostics` 明确拒绝自动豁免；不得仅凭节点/单元存在将其改标 SUCCESS。荷载最终独立验证代码已接入，但本项目新九阶段链中的 Load 尚未真实执行，不能声称其验收通过。

## 真实脚本变化实验

运行 `scripts/validate_batch_runner_v4.py`，证据目录：

`.batchrunner/v4-validation/80ab0f2bbf444e9abc704f44ceaa9b3f`

baseline：前七步全部 REUSED；modified：临时在 BC PY 末尾设置 Model.description 标记，前六步 REUSED、BC RERUN；独立重新打开的 CAE 中 description 与新标记完全一致；restored：恢复原始源文件字节后 BC 再次 RERUN；unchanged：前七步全部 REUSED。

每次阶段性交付均 PASSED。所有顶层原输入文件哈希与测试前一致。实验没有改变几何参数，证明的是最新脚本确实执行并持久保存；不将其描述为修改了工程几何。Mesh/Load 因本实验显式 through=7 而 SKIPPED，默认全链阻断行为另行真实验证。

## 可用的阶段性交付

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20261019\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07.cae`

大小 **860,160 字节**，Model `DP_ANG14_FA03521S-T0104-02`，13 Parts（含 Tie 新增隔离 Part）、17 Instances、10 个报告命名孔特征，12 个 Step07 Tie。

执行状态 7/9 PARTIAL_SUCCESS；CAE 保存 SAVED；ABAQUS 2020 独立重开 **420 项检查 PASSED**。该文件完成到 BC，未包含已验收的 Mesh/Load。文件 SHA-256：`44b46475c98dc220dffb079672d19149efeadae06345a6388a0ac1d25d548aca`。完整运行遇到网格审查时，这份已验证文件保持不变。

## GUI 与开发版 EXE

- GUI：`dist/CADtoCAE_BatchRunner_V40/CADtoCAE_BatchRunner_V40.exe`
- CLI：`dist/CADtoCAE_BatchRunner_CLI_V40/CADtoCAE_BatchRunner_CLI_V40.exe`
- 构建日志：`outputs/v40_build.log`。
- GUI EXE 隐藏启动烟测 PASS：`outputs/v40_gui_exe_smoke.json`。
- 实际根目录 GUI 九列、状态更新、当前阶段性路径检查 PASS：`outputs/v40_gui_scan.json`。
- 打包 CLI 扫描成功；批次 `20261020-075900-076853f9` 使用 `--through 7`，前七步全部 REUSED，独立重新打开和交付 PASSED：`outputs/v40_packaged_cli.log`。

需要用户人工检查 GUI 交互。九项目是 Mock/发布测试，真实 Abaqus 验证的是上述一套项目。未提交 Job、未提取 ODB、未改其他 Worktree、未 commit/push/PR。旧历史文件未自动迁移或删除。

后续完整验收需要在 Step07 原开发任务中处理网格警告或提供满足原质量规则的项目，然后重新生成对应 PY；BatchRunner 将从最早变化阶段自动续跑。不得将诊断 CAE 人工伪装成成功检查点。
