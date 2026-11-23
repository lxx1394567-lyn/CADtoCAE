# V0.3.5：两个连续静力计算步

本版 Step07-01 依次创建 STEP07_PRELOAD（Previous=Initial）和 STEP07_LOADING（Previous=STEP07_PRELOAD）。两步均为 Static General，NLGEOM OFF，Time Period=1，Automatic，Initial=0.01、Minimum=1e-7、Maximum=1、Maximum increments=1000000。不施加预紧力或任何外荷载，不创建 BC、Mesh、Job。

请使用 dist/V0.3.5/CADtoCAE_Step07_AnalysisSetup/CADtoCAE_Step07_AnalysisSetup.exe 生成新版脚本。旧 PY 的内嵌代码不会自动更新。

若当前已有 STEP07_STATIC、STEP07_PRELOAD 或 STEP07_LOADING，立即报告冲突，不自动删除或覆盖。请保存当前工作，人工选择只含 Initial 的计算步前模型工作副本（例如已验收单步版本对应的 _before_step.cae），确认连接齐全后再 File → Run Script。不要在已有 STEP07_STATIC 的 v4 CAE 上直接期待自动替换。

默认 CURRENT_SESSION_DEBUG 保留 MDB；INDEPENDENT_CAE 独立进程模式保留。两模式共用同一创建及验证函数。创建中途失败时按 Loading→Preload 的逆序回退仅本次新增步骤，验证原模型及步骤清单；不静默保存半成品。

逐一在 Edit Step 的 Basic/Incrementation 检查参数，并在 Step Manager 检查 Initial→STEP07_PRELOAD→STEP07_LOADING。对应报告 step_parameters 为包含两步的列表，added.steps=2。后续 Step07-02～05 未启用。

以下历史说明中的单步名称和旧参数已被本段替代，文件保护、当前会话与原生 saveAs 限制仍适用。

# V0.3.4 当前会话模式（取代旧版默认独立加载说明）

默认“生成当前会话 PY”：File → Run Script 时只使用当前 abaqus.mdb；目标 Model 必须与完整项目编号一致。不会打开磁盘输入 CAE、不会关闭当前 MDB、不会重新执行前序步骤。如果缺少目标 Model 或已有计算步，明确停止。

执行前打印模式、恢复备份和目标 CAE 路径。在 CAE_Results 中先保存 `<项目>_step07_01[_vN]_before_step.cae`（当前会话修改前恢复副本），之后只新增 STEP07_STATIC、检查模型保留，再 saveAs 新阶段 CAE。当前会话仍打开，数据库路径会更新为新阶段 CAE。出错时回退本次新增步骤并校验；不自动保存失败状态，无法恢复时明确要求使用恢复副本。若保存过程中产生部分输出，报告标记失败，不能当作验收成果。

报告模式 CURRENT_SESSION_DEBUG，input_cae_used=false；生成时扫描的磁盘 CAE 只作为项目信息，不代表当前内存状态。重开验证必须另开进程或由用户完成，当前脚本不会为验证而关闭用户 MDB。报告 reopen=PENDING_EXTERNAL_VERIFICATION 是预期状态。

“独立 CAE 自动运行”生成 execution_mode=INDEPENDENT_CAE 的独立版本，在新进程读取指定 CAE并重开检查。两种模式共用 s7_apply_static_step，参数一致。默认人工脚本禁止送入自动入口，避免模式混用。

版本只在生成时分配，运行时绝不偷偷改号。已有 CAE、报告、日志或恢复副本就保留整套旧版本并生成下一个版本；旧脚本遇到路径占用时明确要求重新生成，且在修改 MDB 前停止。旧 PY 不会因更新 EXE 自动改变，必须运行新版生成的文件。

以下为保留的扫描及目录约定；旧版独立加载操作只适用于独立 CAE 自动运行。

# Step07 V0.3.4 使用说明

当前仅启用 Step07-1。默认生成独立 PY，不运行 ABAQUS；自动运行按钮保留用于回归。阶段 2～5 未实现、未启用。

1. 启动 dist/V0.3.4/CADtoCAE_Step07_AnalysisSetup/CADtoCAE_Step07_AnalysisSetup.exe。分发时保留整个同名目录。
2. 选择包含 Step04 装配摘要的工作文件夹，扫描并选择项目。查看文件检查列和日志中的来源、缺失或歧义原因。
3. 点击“生成当前阶段 PY”。GENERATED 仅代表脚本生成，尚无输出 CAE。
4. 在 ABAQUS/CAE 2020 中 File → Run Script，选择输出目录内 `<完整项目编号>_step07_01_step.py`。无需修改路径；脚本加载记录的输入 CAE，不依赖当前会话模型。请先保存自己正在编辑的模型。
5. 查看工作目录的 `CAE_Results/<完整项目编号>_step07_01.cae`、根目录 `<完整项目编号>_step07_01_report.json` 和 `<完整项目编号>_step07_01.log`。报告 SETUP_COMPLETE / reopen PASS 仍需人工验收，不代表工程求解通过。
6. 脚本禁止覆盖已有输出；再次测试请在 EXE 重新生成。未运行且内容一致则复用；已有结果或内容变化时成套使用 _v2、_v3 后缀，旧文件保留。输入移动或内容改变后必须重新扫描生成。

## 扫描及匹配

以递归发现的 `*_assembly_summary.json` 内容 project_id 为主，读取 model_name、structure_type、instances（角色、Part、定位）和 assembly_points。分别报告项目识别、装配数据完整性、CAE 可用性和当前阶段就绪状态。角色/定位缺失可仅测试计算步，缺少目标模型或实例名称则停止。

CAE 在摘要目录及其子目录匹配完整项目编号边界，不跨其他摘要目录配对。忽略隐藏运行目录、Step07 输出、备份、临时及历史目录，以及带 step07/backup/test/old/temp 标记的 CAE。无 delivery.json 也可使用；非完整编号文件名须用同名 `.source.json` 声明 project_id、model_name、upstream_stage（Step04/Step05/Step06），建议附 sha256。

可选 delivery.json 必须状态 PASSED/SAVED、Model 和哈希相符。兼容 BatchRunner 记录：数字阶段 2=Step04，3=Step05，4/5=Step06，不能按模块编号直接解释。优先有明确阶段记录的候选，再优先较高上游阶段；同优先级不同内容报告歧义。没有记录时只有唯一内容候选才接受；文件名 step04/05/06 只作来源声明，不作工程验证。任何选择都不依赖修改时间。相同内容副本按路径确定性选择。

没有荷载或连接计划不阻止 Step07-1。实际执行核对摘要 Model 和实例名称；只新增 STEP07_STATIC（Static General，NLGEOM OFF，初始/最大增量 1，最小 1e-7，最大增量次数 1000，时间 1）。不创建 BC、Mesh、Load、Job，不改变连接或增加 RP 约束。

统一名称由 src/cadtocae/step07_rules.py 的 STAGE_NAMES 管理：step07_01_step、step07_02_bc、step07_03_mesh、step07_04_load、step07_05_inp。后四项仅保留名称，不含本轮实现。

报告和生成计划记录上游阶段、依据、候选路径和 SHA256。所有本阶段结果标记 DEBUG_MODEL、engineering_verified=false；Step04 模型不具备连接工程验收资格。先人工检查，再授权下一阶段。


## V0.3.4 扁平输出

以 GUI 所选工作目录为输出根目录，即使摘要在子目录发现也保持此规则。PY、版本对应 plan/report/log、生成记录均带完整项目编号，直接位于根目录。CAE 及保护原模型用的 `<项目>_step07_01[_vN]_input_copy.cae` 位于 CAE_Results；副本不作为后续阶段输入。无 Step07_Results、Batch 或随机 S1 子目录。原有历史目录不移动、不删除。

版本示例：`<项目>_step07_01_step_v2.py` 对应 `CAE_Results/<项目>_step07_01_v2.cae`、`<项目>_step07_01_v2_plan.json`、`<项目>_step07_01_v2_report.json` 和 `<项目>_step07_01_v2.log`。每个版本仅运行一次；失败记录也保留，再生成取下一版本。日志在运行前以独占方式创建，重复执行不会覆盖旧日志、报告或 CAE。自动运行直接使用所选项目的 plan 定位报告，不能读取其他项目的结果。

各阶段尚未实施的验收衔接保持禁用；未来必须明确确认具体项目和输出版本，不自动把最新版本当成已验收。生成记录和 GUI 会话记录同样使用项目编号及递增版本，避免重跑覆盖。所有参数不变，仅修改文件管理。


### ABAQUS saveAs 原生行为限制

真实探针发现 saveAs 可能改变当前打开 CAE 的字节（旧模型库存及 Initial 步重开一致，但文件 SHA256 变化）。当前会话模式因此先另存 `_before_step_disk.cae` 原始磁盘字节副本，再保存 `_before_step.cae` 当前内存模型恢复副本；两者用途不同。报告记录源文件前后哈希及警告，不擅自回写原文件。不能承诺原生 saveAs 使当前打开的旧 CAE 逐字节不变；如必须维持旧文件字节，请先在用户自己的工作副本会话中调试。已有 Step07 输出版本不会被替换。
