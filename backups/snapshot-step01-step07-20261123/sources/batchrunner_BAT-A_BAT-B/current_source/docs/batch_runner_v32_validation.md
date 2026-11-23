# BatchRunner V3.2 实际诊断与验证（2026-10-17）

工作区：`CADtoCAE-BatchRunner`，分支：`feature/batch-runner`。未修改 main，未修改原始 Hole/Connector 算法。

## 修改前的实际诊断

测试根目录：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017`。

项目：`DP_ANG14_FA03521S-T0104-02`，key：`53e5e91d7ef68a5378bd`。

1. 历史成功判定依赖脚本/输入/契约/执行器/上游指纹、成功收据、检查点哈希和报告 artifacts 哈希；不存在仅凭 CAE 存在即复用的正常路径。
2. 原算法已使用 SHA-256，不依据时间戳或大小。因此没有证据支持本次“修改过的 PY 没有执行”的假设。
3. 最近问题批次 `20261017-094131-0dc6c7d2`：Step1 `reused=true`，沿用 `20261017-092856-a505bf42/…/step1/checkpoint.cae`；Step2～Step4 均实际执行，有各自 started/ended、返回码、新 CAE 和运行日志。后三步历史状态 STALE。
4. 批次 `093843` 与 `094131` 的 Assembly 运行副本哈希相同；最早 `092856` 的副本不同。Analysis 在 `094131` 又发生变化。旧算法把可选生成来源/Assembly summary 也纳入指纹，存在不必要重跑问题，而不是本次日志所证实的漏跑。
5. 每次开始会重新 inspect/scan/check；executor 从源文件生成新批次 stage.py，重定向输入/报告/保存接口，由 worker.py 执行；不会选择旧批次 stage.py。但 V3.1 缺少完整的源/运行副本指纹明细及 GUI REUSED/RERUN 区分。
6. 本轮诊断时 Step1～Step3 当前脚本与最近运行副本适配后相同；Hole 已由 0.2.6 更新为 0.2.9，当前扫描能识别 Step4 STALE。Connector PY 此时已出现，因此磁盘状态与用户描述的旧运行时 MISSING 不同。
7. 最新失败并非 Hole 验证失败，也非 Step5 缺失：Step4 候选已通过独立验证，发布失败原因是 `Interrupted delivery target changed externally; manual review required`。
8. 内部 pending 的旧哈希为 `9089d3e8…`、待发布新哈希为 `f435f402…`，诊断时实际 step04.cae 哈希为 `e147b33a…`，与两者都不同。无法仅从记录确定外部变化原因，不能断言由用户编辑或某个程序造成。旧事务阻断了新模型交付，用户打开的仍可能是旧交付文件。

原始记录：`.batchrunner/history/53e5e91d7ef68a5378bd-latest.json` 在运行后会更新；不可变旧批次记录保留于 `.batchrunner/20261017-094131-0dc6c7d2/53e5e91d7ef68a5378bd/record.json`。旧交付验证日志位置记载在其中 `delivery.logs`。

## 修改模块

- state.py：v2 指纹明细（源 PY、runtime/config 输入、上游指纹与检查点 SHA、契约、执行器版本）；排除 generation-only 来源、非读取的历史报告和最终交付文件。
- dependencies.py/scanner.py：扫描时源字节哈希、更新计划/原因；说明内嵌数据脚本需要重新生成才能应用 Excel/JSON 生成来源变化。
- preflight.py/runner.py：按新哈希链判定 REUSED/RERUN，显示 STALE 原因，开始重新读取磁盘；执行前与执行后检查变更；从有效前置检查点副本运行，不叠加旧最终模型。
- executor.py：每批次保存 source_snapshot.py 与 execution_files.json，记录源路径/SHA、实际 stage.py 路径/SHA、worker 路径/SHA；执行副本与审计文件加入 artifacts 哈希校验。包装器内容保留，适配接口版本升级。
- publication.py：仅对同一个已登记目标、在新候选已通过验证时，备份外部变化后的当前字节及旧 pending，再安全更新；未验证候选不能解除保护，未知文件不自动认领。
- delivery_worker.py：验证收据增加实际 Model.description，用于证明变更确实持久保存。
- GUI/CLI：REUSED、RERUN/SUCCESS、STALE 及原因和更新计划；CSV 区分复用；高级“执行至 Step”/`--through` 可限制验证范围，范围外标记 SKIPPED，不伪装 MISSING。

旧版本只有汇总指纹，没有可审计的分项明细。V3.2 首次运行保守重建一次建立新基线；后续未修改运行可复用。生成来源变化不会自动更新 PY 内嵌数据；这类文件要先由生成器重新生成 PY。实际 runtime JSON/Excel 变化自动使消费阶段及下游失效。

## 测试结果

Mock 先行：81 项 BatchRunner 测试通过，包括逐阶段修改与 Step5 缺失、JSON/Excel 实际输入、同大小并保留时间戳、缓存扫描后修改、缺前置检查点、旧运行副本、失败阻止后续、9 项目独立失效、受管理的外部变化交付恢复。日志 `outputs/v32_mock_tests.log`。

真实 ABAQUS 2020，使用原测试目录与原源文件：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\.batchrunner\v32-validation\f338425599b040b6b8ee2527be71e3cc`

该目录保存 baseline、modified、restored、unchanged 四份记录和输入哈希、原始 Assembly 备份。

- 首次建立新指纹基线，执行当前 PY（含新 Hole 0.2.9），成功交付 Step4。
- Assembly 附加临时、非几何的 Model.description 标记；计划和真实执行均为 Step1 REUSED，Step2～Step4 RERUN。
- 独立重新打开交付副本，实际 description 等于新标记；执行源 SHA 与修改后的文件一致。证明新脚本修改写入了 CAE，并非仅验证进程返回码。
- 自动恢复 Assembly 原始字节，重跑 Step2～Step4，正常交付不带测试标记的最终阶段模型。
- 再次运行无任何修改：Step1～Step4 全部 REUSED，交付 PASSED。
- 首轮变更实验范围为 through=4，Step5 准确记为 SKIPPED；真正 Step5 缺失由 Mock 覆盖。随后按用户确认继续验证新出现的 Step5，结果见下文。
- 所有顶层原输入文件最终哈希与测试前一致；其他 Step07 交付文件未变化。旧被外部修改的 step04.cae 已备份到内部 superseded 事务归档。

首轮阶段性模型（完整交付后已转入内部归档）：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_step04.cae`

大小 544768 字节；Model `DP_ANG14_FA03521S-T0104-02`；9 Part、17 Instance、10 个报告命名孔特征；126 项独立检查通过。PY 执行 PARTIAL_SUCCESS、CAE SAVED、独立验证 PASSED、交付 PARTIAL_SUCCESS。

运行脚本：`scripts/validate_batch_runner_v32.py`。它临时写入模型描述、保护源文件并在最终交付前恢复原字节；若检测到外部并发改动则拒绝覆盖源文件。

9 项目调度属于 Mock 测试；真实工程项目只验证上述一套。已验证五阶段模型对象与报告一致；未验证额外 Step07、刚度标定或求解结果。旧 step06test2 迁移未在本轮执行。

## 用户确认后的 Step5 与 EXE 验证

批次 `20261017-110808-46cbf308`：Step1～Step4 REUSED，Step5 RUN/SUCCESS。独立 ABAQUS 2020 重新打开验证 PASSED，完整交付 SUCCESS。

最终文件：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_final.cae`。

大小 647168 字节，Model `DP_ANG14_FA03521S-T0104-02`；9 Parts、17 Instances、10 个报告命名孔特征、8 Connectors/Wires、16 RPs、16 Couplings、1 Connector Section。343 项独立检查全部 PASSED，数量来自阶段报告与模型对象比对。

构建后的 CLI EXE 再运行智能模式（批次 `20261017-110952-e1525d4f`）：五阶段全部 REUSED，独立模型验证和交付再次 PASSED。GUI EXE 隐藏启动烟测 PASS（`outputs/v32_gui_exe_smoke.json`），真实 GUI 扫描验证见 `outputs/v32_gui_scan.json`。尚需用户人工检查 GUI 交互和模型工程效果。

全仓测试 240 项：239 通过，1 项因缺少已有 PDF 样本跳过。日志 `outputs/v32_full_tests.log`。

开发验证版：
- `dist/CADtoCAE_BatchRunner_V32/CADtoCAE_BatchRunner_V32.exe`
- `dist/CADtoCAE_BatchRunner_CLI_V32/CADtoCAE_BatchRunner_CLI_V32.exe`

构建日志 `outputs/v32_build.log`；真实 Step5 日志 `outputs/v32_step5_validation.log`；打包 CLI 集成日志 `outputs/v32_packaged_cli.log`。未 commit、push 或创建 PR。
