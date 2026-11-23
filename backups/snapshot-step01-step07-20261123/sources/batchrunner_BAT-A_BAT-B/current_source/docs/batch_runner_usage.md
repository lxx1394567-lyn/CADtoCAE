# BatchRunner V4.0 使用说明

选择项目根目录 → 扫描/刷新 → 一键开始。默认智能续跑，共九个阶段：

Part → Assembly → Analysis → Hole → Tie → Step → BC → Mesh → Load。

Step06 旧 Connector、Hoop/Brace Connector、Step07 INP 导出均不执行。原始文件保留。

## 文件准备

每套项目使用同一个完整项目编号，九个 PY 放在同一项目目录；一个根目录可包含多套项目。准确后缀和依赖见 batch_runner_v4_audit.md。Step07 使用当前生成器的 `_step07_01_tie_setup.py` 至 `_step07_05_load_setup.py`，不能混用旧版 pipeline/带版本号的历史脚本。

Step07 的装配信息与参数内嵌在 PY 中；Load JSON 必须与 PY 指定路径、项目身份和 SHA-256 相符。若修改了生成用 Excel 或 Load JSON，请先重新生成相关 PY；不能只更改 JSON 而继续使用记录旧哈希的脚本。运行时缺少输入会显示路径；重复项目/冲突不按时间猜选。

过程文件、Step07_Logs、CAE_Results、.batchrunner 等内部目录不作为源码项目扫描。

## 智能续跑和状态

每次开始重新读取磁盘文件与 SHA-256，从最早失效的阶段和最近有效前置检查点恢复。REUSED 是可靠历史结果复用；RERUN / SUCCESS 是本次重新执行成功；STALE 是历史结果失效；MISSING 是脚本暂缺；MISSING_INPUT 是实际输入缺失；BLOCKED 是前置条件不满足。旧五阶段流程首次升级保守重建，不使用 Connector 检查点作为 Tie。

只有九个阶段全部执行成功且最终模型通过独立重开验证，才交付完整 SUCCESS。缺后续脚本时允许前面的连续成功阶段交付 PARTIAL_SUCCESS；中间缺阶段时不跳过它执行下游。界面显示 7/9 等实际完成数量，可横向滚动查看全部九列。

REVIEW_REQUIRED 表示原 Step07 网格质量规则要求审查，**不是成功**。不自动放行 Load，不更新最终模型。内部 review_only.cae 仅用于诊断，不能作为断点续跑的有效上游。BatchRunner 不豁免网格警告，也不修改建模算法。

## 模型交付

完整模型固定保存到 `<根目录>/CAE_Results/<项目编号>_final.cae`。部分模型使用 `_stepNN.cae`，NN 是 BatchRunner 执行序号，例如 `_step07.cae` 是第七阶段 BC，不表示整个 Step07 模块完成。

只有候选模型保存并通过 ABAQUS 2020 独立重新打开检查后才安全替换固定交付。失败或 REVIEW_REQUIRED 保留原有已验证成果。已存在但未被程序登记的同名文件不会自动覆盖；历史迁移必须先查看清单并确认。旧五阶段最终模型仅标为历史成果，不能认定新九阶段完整成功。

GUI 提供打开 CAE、打开结果目录和交付详情；当前阶段性结果与此前完整成果分别显示。打开 CAE 使用配置的 Abaqus GUI 启动器。文件被占用时保留旧文件并提示关闭占用后重试。

检查点、源脚本快照、实际运行副本及SHA-256、每阶段日志、报告、交付验证结果、备份均在 `.batchrunner`；不要删除它们来强制更新。

## 高级和命令行

高级设置保留输出目录、Abaqus 启动器、调度器配置、全量/续跑/指定阶段、执行至阶段（1～9）、停止策略与迁移。

```powershell
CADtoCAE_BatchRunner_CLI_V40.exe scan "F:/项目根目录"
CADtoCAE_BatchRunner_CLI_V40.exe smart "F:/项目根目录"
CADtoCAE_BatchRunner_CLI_V40.exe smart "F:/项目根目录" --through 7
CADtoCAE_BatchRunner_CLI_V40.exe from "F:/项目根目录" --start 5
```

新流程不提交 Job、不运行求解器、不提取 ODB。对象和几何验证不等于工程设计或求解结果验收。当前 20261019 项目的实际测试结果及网格限制见 batch_runner_v4_validation.md。
