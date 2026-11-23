# Step07 V0.3.3 扁平输出验收记录

仅调整文件输出、命名、重复运行保护和自动模式报告定位；计算步创建参数及行为未变。没有开发 Step07-2～5，没有提交 Job，没有修改 BatchRunner。仍在 feature/step07-analysis-setup；未提交、推送或创建新 Worktree。

## 交付路径

- EXE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\V0.3.3\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe`
- 已执行 PY：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01_step.py`
- 输出 CAE：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\CAE_Results\DP_ANG14_FA03521S-T0104-02_step07_01.cae`
- 阶段报告：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01_report.json`
- 运行日志：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01.log`
- 可供人工 File → Run Script 的未执行版本：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\20161017\DP_ANG14_FA03521S-T0104-02_step07_01_step_v2.py`

旧版 EXE 正在用户桌面中打开，因此新版单独发布到 dist/V0.3.3；旧版窗口及文件保留。请启动上述新版路径，并保留其整个文件夹。

## 实测范围及结果

唯一真实算例：DP_ANG14_FA03521S-T0104-02，工作目录为 CADtoCAE-EXE-Testing/20161017。使用真实冻结 EXE 的 Tk --ui-smoke 回调完成扫描、选择和默认生成；配置不可用 ABAQUS 命令，确认默认生成不启动 ABAQUS。PY 出现在根目录，STAGE1_PLAN.output_dir 为根目录，output_cae 为现有 CAE_Results 中的完整编号文件。

随后通过生产自动执行入口调用 ABAQUS 2020 cae noGUI，执行上述 EXE 生成的原始脚本，并从项目专属路径正确读取报告。SETUP_COMPLETE，reopen PASS，preservation PASS。只新增 1 个 STEP07_STATIC，BC/Load/节点/单元/Job 新增数量均为 0；Static General，NLGEOM OFF，初始/最大增量 1、最小增量 1e-7、最大增量步数 1000。

根目录成功生成项目专属 report.json 和 .log；自动模式另有项目专属 _console.log。CAE_Results 中保护上游用的 _input_copy.cae 保留，不作为后续阶段输入。没有新增 Step07_Results/Batch/S1 多层目录。

34 项自动化测试通过，包含多项目命名互不干扰、相同脚本复用、人工修改脚本不覆盖、已有 CAE/报告触发 _v2、版本对应关系、自动执行 plan 传递。第二次真实 EXE 生成产生 _step_v2.py，尚未执行；第一版 PY、CAE、报告和日志均保留。自动入口重复执行第一版被明确拒绝，旧结果哈希不变。

已检查工作目录原有 219 个文件（包括 Step07_Results 历史成果），全部存在且 SHA256 不变；上游源码快照 71 项全部一致。构建清单哈希与当前源码一致。核验记录见 step07_runs/v033/acceptance_audit.json。

## 尚待人工验收

Windows computer-use 工具连续两次返回 “foreground window did not report a process id”，未能完成真实 File → Run Script 菜单点击。不能将 noGUI 技术验证说成手工菜单验证。用户可在 ABAQUS/CAE 2020 保存当前会话后运行未执行的 _v2.py，输出对应 _step07_01_v2.cae；或直接打开第一版 CAE 检查。已执行第一版再次运行会拒绝覆盖，这是预期保护。

模型仍为 DEBUG_MODEL，尚未工程验收。后续阶段禁用，将来必须明确确认具体项目及阶段版本，不能自动把新版本当作已验收输入。本轮停止开发，等待人工反馈。
