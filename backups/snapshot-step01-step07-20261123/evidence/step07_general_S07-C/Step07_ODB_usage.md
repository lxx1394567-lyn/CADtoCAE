# Step07 0.9.0：ODB 结果提取

第七阶段是独立后处理，不要求当前 MDB 包含模型，也不执行 Step01～06。

## 操作

1. 启动 `dist/CADtoCAE_Step07_AnalysisSetup/CADtoCAE_Step07_AnalysisSetup.exe`，选择工作目录。可扫描并选中项目以带入 Assembly Summary；也可在后处理窗口单独选择摘要。
2. 阶段下拉框选择“07 ODB结果提取”，点击“生成 PY”打开后处理窗口。
3. 选择已经计算完成的 ODB 和对应 Assembly Summary，设置项目输出目录。
4. 填写便于区分的结果 Job ID 和工况说明。例如 `LUAN_POS_100`、`LUAN_POS_080`、`LUAN_POS_075`。Job ID 留空时使用 ODB 文件名；程序不凭文件名猜测荷载、折减系数或厚度。
5. 可点击“读取分析步/帧”查看可选项。分析步留空、帧为 `-1` 时选最终分析步的最后一个同时具有 S、U 的有效帧。帧编号从 0 开始。若需要对比工况，可填写相同的应力色阶上限（MPa）。
6. 点击“生成后处理 PY”，在 Abaqus/CAE 2020 使用 File → Run Script 手工运行；或点击“执行后处理（独立进程）”。后者只启动独立 CAE 后处理进程，界面显示进度及最终状态，不操作已打开的用户 MDB、不提交求解。
7. 点击“打开结果文件夹”。结果位于工作目录 `Step07_ODB_Results/<JOB_ID>`；同名重跑使用 `_v2` 等清晰版本，不覆盖已有结果。

生成脚本位于项目根目录：`<PROJECT_ID>_step07_07_odb_postprocess.py`。更新脚本时旧内容保留到 Step07_Archive。自动执行产生的 Abaqus 运行文件单独放在 `Step07_ODB_Results/Runtime_Logs`。

## 输出和统计口径

- Luan 模型输出整体 S、U，4 个檩托 S，3 组抱箍 S，共 9 张 1600×1000 PNG。每个抱箍组包括摘要所定义的全部半片，程序核验实际显示实例集合。
- Excel 有 Overall、PurlinSupport、HoopGroup、CalculationInfo 四张表；JSON 保留更完整的实例映射、每个半片峰值、单元标签、积分点及显示峰值。
- 数值应力为所有已保存截面点的**原始积分点 Mises 最大值**；Pa 转 MPa。位移取原始节点 U 模量，m 转 mm。
- 云图使用临时内存中的换算场，Abaqus 负责真实渲染。应力采用未变形构形，关闭节点平均；壳体显示 SNEG。云图会发生外推，图例峰值不等于原始积分点峰值。每张图同时写明原始峰值，JSON/Excel 分别记录两种数值。位移图变形比例为 1。
- 积分点坐标未输出时留空，并明确标记无法直接获得，不将单元中心冒充积分点位置。提供控制实例、单元和积分点编号供人工定位。
- 目前没有已确认的材料强度输入，因此安全系数为 `PENDING_MATERIAL_STRENGTH`，不自动套用 235 MPa。
- 其他支架按各自 Assembly Summary 识别实际檩托数和抱箍组数；本轮真实运行验证仅覆盖 Luan/SP_DC。

## 安全与状态

0.9.2 新增“基底反力”中文工作表：提取与应力同一步、同一帧的全局 RF1/RF2/RF3（N），并计算矢量合力。SP_SC/SP_DC 读取 STEP07_RP_BASE，DP 读取 STEP07_RP_BASE_FRONT 与 STEP07_RP_BASE_REAR。仅使用这些基础 RP 集合，不重复计入 Coupling 自动集合或其他位置约束。RF 缺失、基础集合缺失或重复、坐标系不能确认时，基底反力单项返回 REVIEW_REQUIRED，合计留空而非零；已有应力/位移提取仍可完成。基底合计不能代替全部约束反力的平衡核验。本轮真实 ODB 验证覆盖 Luan 单基础，双基础矢量求和及去重已作单元测试。

源 ODB 以只读方式打开，运行前后校验 SHA256，不创建 CAE，不修改模型和结果字段。显示换算仅保存在 ScratchOdb；临时注释不保存到 ODB。手工执行时不会关闭用户原先已打开的 ODB；若它以可写方式打开，脚本会停止并提示用户处理。

`SUCCESS` 仅表示提取、云图、Excel 和源文件保护检查成功。它不代表材料、网格、Tie 或应力结果已获得工程验收。计算未完成、数据缺失、映射错误、渲染失败均返回 FAILED 并保留诊断日志。缺失匹配 DAT 时明确报告诊断信息不完整。

本次实现依据 Abaqus 的 [ScratchOdb 接口](https://abaqus.uclouvain.be/English/SIMACAEKERRefMap/simaker-c-scratchodbpyc.htm)存储临时显示场；只读 ODB 的临时注释采用官方[视口注释机制](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-cnvannotateview.htm)，并经过真实 2020 验证。
