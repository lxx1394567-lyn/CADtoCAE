# BatchRunner V3 实际验证记录

日期：2026-10-11。开发 worktree `CADtoCAE-BatchRunner`，分支 `feature/batch-runner`。无 commit/push，未修改 main、其他 worktree 或原始 Hole/Connector 算法。

## 当前交付结果

真实环境：ABAQUS 2020，启动器实际解析至 `D:\Software\SIMULIA\Commands\abaqus.bat`。

项目 / Model：`SP_SC_ANG18_11042210101041S-T0202`。

当前 GUI / EXE 运行记录所指向的完整模型：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\step06test2\CAE_Results\SP_SC_ANG18_11042210101041S-T0202_final_2fba535f2a6f2582.cae`

大小 495616 字节（484 KiB）。使用版本后缀是因为此前调试已生成同名 final.cae，安全策略保留全部历史文件。

- PY 执行：5/5 SUCCESS。
- CAE 保存：SAVED。
- 独立重新打开验证：PASSED，319 项检查。
- 项目交付：SUCCESS。
- Model 内 9 个 Part、15 个 Instance。
- 9 个报告命名开孔特征，核对未抑制、几何切除面积/体积及 Hoop 保存结果。
- 8 条 Wire/Connector，16 个 RP、16 个 Connector Coupling、1 个 Connector Section，核对精确对象集合、区域几何、RP 坐标及 SectionAssignment。

打包 CLI 最后运行批次：`.batchrunner\20261011-091239-ebd3c4d1\ef80becbd3bd34ac0a4b`，五步 `reused=true`。模型保存与验证收据位于本批次 `delivery` 及 CAE 同名 `.delivery.json`。

## 原 V2 检查点复用

专门从审查时的原 V2 五个检查点导出，完全没有调用 execute 或重新建模：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\step06test2\CAE_Results\SP_SC_ANG18_11042210101041S-T0202_final_3ab39bc2b379d7f6.cae`

同样 495616 字节，独立验证 PASSED。记录：`outputs/v3-real-checks/retained-v2`。

## 部分与负向验证

- 从真实成功链导出前三步：测试根目录 `CAE_Results\SP_SC_ANG18_11042210101041S-T0202_step03.cae`，PASSED。
- 将真实前三个 PY 复制到隔离目录 `outputs/v3-partial-project`，实际执行 Abaqus：前三步 SUCCESS、后两步 MISSING，输出对应 step03.cae，执行状态及项目状态均 PARTIAL_SUCCESS，交付 PASSED。批次 `20261011-091044-18a5d26c`。
- 用 Step3 文件冒充完整模型：独立验证 FAILED。
- 人造损坏 CAE：无法正常打开，独立验证 FAILED。
- 以上检查明细：`outputs/v3-real-checks/results.json`；可通过 `scripts/validate_batch_runner_delivery.py` 针对本测试夹具重复验证。
- 重复智能运行全部复用检查点；相同内容交付文件复用，但执行独立验证。
- 9 项目独立文件、历史文件保护、验证失败、无真实执行器不得成功、文件损坏/丢失拒绝打开、GUI 命令参数等属于单元测试，不宣称完成 9 套真实支架的 Abaqus 验收。

## 自动测试与 EXE

- BatchRunner 专项 62 项通过（含 V3 新增 12 项）。模拟 CAE 均在临时目录，不能作为真实交付依据。
- 项目构建 Python 环境全量 221 项：220 通过，1 跳过（缺少既有样例 PDF），0 失败。日志 `outputs/v3_build_runtime_tests.log`。
- 系统 Anaconda 的另一轮全量测试有 40 个既有 Excel 测试临时文件清理错误及未关闭句柄警告，日志 `outputs/v3_full_tests.log`；未修改不相关 Excel 算法。在项目打包环境复核全部通过。
- 构建日志：`outputs/v3_build.log`。
- GUI EXE：`dist/CADtoCAE_BatchRunner/CADtoCAE_BatchRunner.exe`。
- CLI EXE：`dist/CADtoCAE_BatchRunner_CLI/CADtoCAE_BatchRunner_CLI.exe`。
- GUI EXE 启动 PASS：`outputs/v3_gui_smoke.json`。
- GUI 真实根目录扫描 / 最终路径 / PASSED / 交付详情 PASS：`outputs/v3_gui_data_smoke.json`。
- CLI EXE 真实 Abaqus 智能续跑及交付 PASS：`outputs/v3_packaged_cli.log`。
- onedir 分发必须保留整个 EXE 所在目录和 `_internal`。

## 验证边界及调试记录

独立 Abaqus 进程打开交付文件的 SHA-256 相同副本，验证进程不执行模型修改或保存。由于 Abaqus 打开 mdb 可能更改数据库内部元数据，副本在打开后的哈希可能变化；证明依据是打开前与交付原件的哈希一致，以及原件/检查点验证前后不变。日志保留初始哈希和副本。

最初测试使用了与原 V2 不同的执行器配置，导致一次五步重建；最初直接打开新生成的 Step3 检查点又改变其元数据，使该新链 Step3 及下游失效并重建。之后改为验证副本，所有智能复测均复用可靠链。原 V2 检查点从未改动，最终五个哈希均与原记录一致；原始 17 个 PY/JSON/Excel/报告文件也与 `outputs/v2_original_hashes.json` 全部一致。

验证只覆盖保存后的建模对象和报告一致性。报告中的 Connector 刚度仍为 TEMPORARY_PRESET；未验证力学标定、荷载完整性或求解结果。未知报告接口不能自动获得 PASSED。GUI 启动/内容做了自动化检查，视觉及工程模型效果仍可由用户人工复核。
