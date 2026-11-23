# Step07 0.2.0 文件夹批处理版交付记录

日期：2026-10-16。此记录替代旧多参数 GUI 的验收说明。

## 成果保护与范围

继续使用 `CADtoCAE-Step07-Development`，分支 `feature/step07-analysis-setup`。旧 GUI/EXE、Step07 源码及 Git 状态备份在 `step07_runs/backups/before_folder_batch_20261016`。未提交、推送、创建 PR，未改动 Step02～Step06。停止了核实属于本工作区的旧测试/求解进程，清单在 `step07_runs/stopped_processes_20261016.json`；保留其他用户 ABAQUS 会话。

与备份逐字节核对，`step07_setup.py`、`step07_runtime.py`、`step07_generate_analysis.py` 未改写。新版仅调整 GUI、新增项目扫描/顺序运行模块和集中规则、更新打包清单。原 ANG18 求解与 ODB 成果保留。

## 最终程序

`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe`

SHA256：`55DD79F0380A61CE103C4CDB931D531A97DB0AE74DD73B18357ECCA32D91C246`。移动时须复制整个文件夹。实际界面截图：`step07_runs/batch_acceptance/gui_success.png`；扫描状态截图：`gui_scanned.png`。

扫描/匹配规则和最小荷载 JSON 接口见 `step07_gui_usage.md`。统一规则为 `src/cadtocae/step07_rules.py`，扫描及荷载适配为 `src/cadtocae/step07_batch.py`。

## 自动化与真实模型测试

- 22 项单元测试通过：`step07_runs/batch_tests_final.log`。覆盖完整编号区分、不同目录禁止拼接、输出/备份排除、CAE 阶段与哈希、时间戳版本、备份后缀排除、单位与重复荷载、输入变化阻止、失败后继续和取消跳过。批次失败继续测试使用替身，不宣称多个真实结构求解通过。
- 最终 EXE 真实启动并通过 GUI 回调回归：显式开发入口 `--ui-smoke` 调用扫描及“一键运行”按钮回调，使用实际 Tk 事件循环、后台线程、打包依赖及真实 ABAQUS 2020；frozen=true，界面轮询 40 次，SUCCESS=1、FAILED=0。
- 该回归不是 Python 源码代替 EXE，也不是原生文件选择对话框的人工验收。人工鼠标点选交互仍请用户确认；桌面自动化点击未可靠触发控件，未将其记为通过。
- 首次 EXE 执行发现长结果目录导致 ABAQUS AIF 写入失败；已去掉重复项目编号目录并增加路径长度诊断。失败记录保留在 `exe_gui_report.json`，最终回归见 `exe_gui_report_release.json`。
- 扫描真实 `CADtoCAE-EXE-Testing/step06test2` 时因缺少 `<完整编号>_static_loads.json` 正确 SKIPPED，证据 `real_project_scan.json`；没有自动补入 -100 N。

## ANG18 EXE 端到端结果

独立输入目录 `step07_runs/batch_acceptance/input` 包含：上轮已完成连接更新的 `upstream_completed.cae` 的文件副本（命名为完整编号_final.cae）、真实配套摘要和连接计划，以及仅为 ANG18 保留的历史流程测试荷载输入。荷载文件记录来源，-100 N 不是生产工程荷载，也没有进入规则模块。

最终输出目录：

`step07_runs/batch_acceptance/input/Step07_Results/Batch_20261016_163918_12baf998/Step07_20261016_163918_c4fdf0fa`

结果：Static General `STEP07_STATIC`；`COLUMN_DOWN_01` 一处底部固定；53,326 节点、36,148 单元（含 10 个连接单元）；PURLIN_LOCAL_01 / STEP06_RP_P01_PURLIN 施加全局 `(0,0,-100)` N；Job `Step07_bad1833c526aee45`；保存新 `step07.cae` 和 INP，连接保留检查 PASS。

实际输出 CAE 已用 ABAQUS 2020 重新打开查询：仅 Initial 和 STEP07_STATIC 两步、1 个固定边界、1 个集中荷载、1 个 Job，Tie 方法仍为 COMPUTED。重开证据在输出目录的 `reopen_check.json` 和日志中。

两个附加转动约束开关和 Tie 修正均关闭，实际附加约束列表为空；没有新建 ODB、没有提交求解。输入 SHA256 前后一致：`8F347FBF96C6EF6C1FD6704B36337BFE65C12C743D2FE2EEBBF0116D12BD4D6D`。

最终审计为 `step07_runs/batch_acceptance/acceptance_audit.json`，核对源代码与打包清单哈希、输入不变、特殊设置关闭及未提交求解。GUI 批次报告、项目报告、运行日志均保存在对应结果目录。

## 尚待人工确认

1. 实际项目的静力荷载接口尚需统一。目前明确支持完整编号_static_loads.json；只有 Excel 或其他形式时会缺失，不猜测力值、方向或位置。
2. SP_DC/DP 及多真实项目尚未完成工程验证。网格规则只是 ANG18 流程参考；没有通过人为约束让其他模型强行成功。
3. ANG18 历史自由转动、Tie 和 118 个未 Tie 节点问题仍需工程检查。新版 SUCCESS 仅指设置与保存完成；不自动提交，也未通过求解消除这些问题。
4. 对无交付清单的唯一 final.cae，扫描只能确认命名归属，运行才检查内部模型。复制交付清单会改变修改时间，因此多个版本的自动选择仍应在项目详情核对；内容哈希不匹配会停止。
5. 中文 CAE 路径/模型名未验证；长路径会明确报错。非标准 RP、已有分析步/边界/荷载的输入仍会被核心拒绝。
