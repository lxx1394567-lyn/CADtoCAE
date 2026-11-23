# BatchRunner V3.1 验证与交付

日期：2026-10-11。工作区 `CADtoCAE-BatchRunner`，分支 `feature/batch-runner`。只调整交付、迁移、GUI、打包和对应测试；未修改 Hole/Connector 建模算法或执行 worker，未提交/推送。

## 实现

- 新候选与验证日志位于根目录 `.batchrunner/deliveries/<key>/runs`；固定最终路径为 `CAE_Results/<project_prefix>_final.cae`。
- 验证成功才发布；新建/重复更新均不产生公开版本后缀或 delivery JSON。
- 新模型失败不替换；未知同名文件需要审查迁移。已登记交付先备份当前字节，再原子替换。
- 同卷候选、旧文件备份、持久化 pending 事务、目标哈希判断和当前交付索引；支持替换完成/索引写入中断后的恢复。
- 部分模型不覆盖完整模型；只保留受管理的当前 partial，升级完整交付时将 partial 内部归档。
- GUI 列表有建模/交付状态和固定路径，区分最新运行与保留的完整/阶段性成果。默认打开完整 CAE；没有完整成果才提示并打开 partial。启动器工作目录也置于内部目录，减少公开目录中的 GUI 会话日志。
- 迁移先生成精确文件清单，由用户确认；结合已验证运行记录和文件哈希选最新完整成果，不按修改时间选择。验证失败不移动原文件。

## 自动测试

- 全仓 232 项：231 通过、1 跳过（既有样例 PDF 缺失）。`outputs/v31_full_tests.log`。
- BatchRunner 73 项通过；最终交付相关 23 项复测通过。`outputs/v31_units.log`、`outputs/v31_final_focused_tests.log`。
- 包含 Windows CreateFileW 实际占用、替换失败旧文件哈希不变、释放占用后重试、替换后元数据中断恢复、输入目录原 CAE 保护、阶段升级、9 项目重复交付仍只有 9 个固定文件。
- 9 项目数量测试为受控模拟发布测试，不宣称已经验收 9 套真实支架的模型。

## 真实 Abaqus 2020 测试

使用当前 step06test2 的真实已验证五阶段检查点，在本 worktree 的隔离交付目录验证，不重新建模：

`outputs/v31-real/53c2fa45/.batchrunner/validation.json`

结果全部符合要求：首次 1 个 final、再次成功仍 1 个 final；运行失败保护原件；真实损坏候选无法打开，旧 final 哈希不变；前三步生成 step03 并保留旧 final；再次完整成功后阶段文件归档，只剩 1 个 final。真实验证继续核对建模对象与阶段报告，所有检查点保持未修改。

## 迁移测试与原目录确认边界

原目录生成的待确认清单：

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\step06test2\.batchrunner\migration\769c632b22434dc59c0b1f0963659b23\plan.json`

包含 8 个 CAE、7 个 delivery JSON。最新匹配成功运行记录为 `20261011-092525-4a315a0d`，选择 `SP_SC_ANG18_11042210101041S-T0202_final_bf6996bef83fd0af.cae`（499712 字节）；计划重新验证后发布为固定 final。其他模型及 JSON 内部归档，不删除。

**原目录迁移仍等待用户明确确认，尚未执行。** 交付前复核清单 15 个原文件哈希均未改变。普通运行不会代替用户确认清理历史版本。

在独立副本 `outputs/v31-migration-fixture/68d224af` 上，使用打包 CLI 执行真实迁移与 Abaqus 验证成功；只剩固定 final，14 个旧版本/JSON 移入迁移归档，原固定 final 另有发布前内部备份。日志 `outputs/v31_packaged_migration.log`。GUI 固定路径和自动选择验证见 `outputs/v31_gui_data_smoke.json`。

## Windows 开发版 EXE

- GUI：`dist/CADtoCAE_BatchRunner_V31/CADtoCAE_BatchRunner_V31.exe`
- CLI：`dist/CADtoCAE_BatchRunner_CLI_V31/CADtoCAE_BatchRunner_CLI_V31.exe`
- 构建日志：`outputs/v31_build_final.log`
- GUI 启动检查：`outputs/v31_gui_exe_smoke.json`

旧 GUI EXE 被占用导致首次原目录打包失败（`outputs/v31_build.log`）；未终止用户进程，改为独立 V31 包目录。构建脚本在清理输出前增加 EXE 独占打开检查，避免后续对正在使用的目标开始重建。

保留完整 onedir 目录和 `_internal`。使用说明见 `docs/batch_runner_usage.md`。模型物理标定、求解结果等仍不属于交付文件管理验证范围。
