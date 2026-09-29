# CADtoCAE Step04 Assembly Script 使用说明

## 单目录工作流

1. 点击 **Select Folder**，选择项目输入目录。
2. 点击 **Scan Projects**。默认只扫描当前层；需要时勾选 **Include Subfolders**。
3. 查看 Project ID / Structure / Input / Capability / Generation / Result。
4. 点击 **Generate Selected** 生成选中项目，或 **Generate All Ready** 依次生成全部可用项目。

每个项目需要同目录、同完整 project_id 的两个文件：

- `<project_id>_create_parts_in_cae.py`
- `<project_id>_coordinate.xlsx`

支持 SP_SC、SP_DC、DP。一个目录可以容纳多个项目。按文件名配对，并核对 Step02 MODEL_NAME、可用的项目/结构元数据和现有装配 preflight。旧坐标模板没有显式 project_id 时，核对可用结构标题及现有坐标解析结果，不从文件夹名称推断身份。

递归扫描时，同一 project_id 的多个候选不会自动选择；Input 显示 Ambiguous Files，选中行可在 Process Log 查看路径。分散在不同目录的输入对也需要先放到同一项目目录。生成物不作为输入。

## 状态和日志

- Ready + Supported：可生成。长度和角度警告仍允许生成。
- Missing Part Script / Missing Coordinate：缺少对应文件。
- Project ID Mismatch / Invalid Coordinate / Invalid Part Metadata / Preflight Error：查看日志中的具体原因。
- Unsupported：结构类型不支持。
- Queued / Generating / Generated / Failed：生成阶段状态。

每次生成前重新扫描和 preflight。某个项目失败后继续处理其他项目，不弹出逐项目阻塞对话框。选中行可查看输入路径、完整警告、错误和报告路径。

批次汇总的 Success 表示无警告生成成功，Warning 表示带警告生成成功，Failed 表示本次生成失败，Skipped 表示未满足 All Ready 条件。四项互斥，其和等于 Total。

## 输出

生成到该输入对所在目录，无需另选输出目录：

- `<project_id>_assembly_frame.py`
- `<project_id>_assembly_summary.json`
- `<project_id>_step04_assembly_script_report.json`

现有直接文件 API 的报告同时保留在 `过程文件/调试文件/`。重复生成会更新同名输出。扫描本身不写输出。

旧的直接文件 API 和 CLI 保留，仍支持原有坐标模板命名；新 GUI 只发现上述标准文件对。

## Abaqus/CAE 人工验证

先运行 Step02 Part Script 创建同名 Model，再运行 Step04 Assembly Script。Step04 只操作同名模型，装配数据内嵌于脚本，不需要额外 assembly_inputs.json。检查装配效果后再进行代码提交。
