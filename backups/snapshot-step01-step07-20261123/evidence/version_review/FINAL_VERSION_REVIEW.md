# CADtoCAE Step01—Step07 EXE / 运行包 / 源码盘点报告

- 盘点日期：2026-11-23（Asia/Shanghai）
- 发起位置：`F:\Codex\Wind Resistance of PV Support Structures`
- main 工作区：`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE`
- main 分支 / HEAD：`main` / `a0092c0`
- main 状态：clean，`main...origin/main`
- 额外核对位置：`F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated`
- 报告性质：第一阶段只读盘点；没有运行 EXE、Abaqus，没有重新打包，没有修改源码、切换分支、提交、打标签或推送。

> 重要：本报告中的“建议候选”不是自动认定的最终版。时间、目录名、版本号、`final` 字样和 EXE 哈希均不能单独证明它就是用户人工验证的最终程序。EXE 的 SHA-256 只识别具体文件，不单独证明源码对应关系。

## 1. 源码对应状态定义

- **A**：有精确构建/发布记录、源码哈希清单或可复核快照支持。
- **B**：有源码入口、构建脚本、同工作区或验证记录等关联线索，但不足以确认当前源码与 EXE 完全一致。
- **C**：无法确认，或发现具体不一致。
- **—**：未发现独立 EXE，不能进行 EXE—源码对应判断。

所有候选 EXE 的 Windows PE `FileVersion/ProductVersion` 均未读到嵌入版本信息；下文版本来自构建清单、文档、目录名或程序自己的验证记录，并注明来源。

## 2. 最终版本待确认总表

| 步骤/功能 | 候选编号 | 主 EXE 完整路径 | 运行包目录 | 选择状态 | 源码对应状态 |
|---|---|---|---|---|---|
| Step01 材料表 OCR | S01-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step01-development\dist\CADtoCAE_Step01_MaterialTable\CADtoCAE_Step01_MaterialTable.exe` | `...\CADtoCAE_Step01_MaterialTable` | 建议候选；待确认 | B |
| Step02 零件脚本/HOOP 修正 | S02-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-fix-step02-hoop-inner-profile\dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe` | `...\CADtoCAE_Step02_PartScript` | 建议候选；待确认 | B |
| Step02 Tcl/Tk 专项包 | S02-B | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-fix-step02-hoop-inner-profile\dist\CADtoCAE_Step02_PartScript_TkFix\CADtoCAE_Step02_PartScript_TkFix.exe` | `...\CADtoCAE_Step02_PartScript_TkFix` | 其他候选 | B |
| Step02 合并前旧包 | S02-C | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step2-part-abaqus\dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe` | `...\CADtoCAE_Step02_PartScript` | 其他候选 | B |
| Step03 坐标工作簿 | S03-N/A | 未发现独立产品 EXE | — | 源码/脚本工作流；待确认是否符合预期 | — |
| Step04 DP + 文件夹 GUI | S04-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step04-dp-assembly\dist\CADtoCAE_Step04_AssemblyScript\CADtoCAE_Step04_AssemblyScript.exe` | `...\CADtoCAE_Step04_AssemblyScript` | 建议候选；待确认 | B |
| Step04 较早 SP_SC/SP_DC 包 | S04-B | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step04-development\dist\CADtoCAE_Step04_AssemblyScript\CADtoCAE_Step04_AssemblyScript.exe` | `...\CADtoCAE_Step04_AssemblyScript` | 其他候选 | B |
| Step05 分析设置 | S05-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step05-development\dist\CADtoCAE_Step05_AnalysisSetup\CADtoCAE_Step05_AnalysisSetup.exe` | `...\CADtoCAE_Step05_AnalysisSetup` | 建议候选；待确认 | B |
| Step05 批量诊断工具 | S05-B | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step05-development\dist\Step05_BatchDiag\Step05_BatchDiag.exe` | `...\Step05_BatchDiag` | 专项辅助候选 | B |
| Step05 单文件夹旧候选 | S05-C | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step05-development\dist\step05_single_folder\CADtoCAE_Step05_AnalysisSetup\CADtoCAE_Step05_AnalysisSetup.exe` | `...\CADtoCAE_Step05_AnalysisSetup` | 其他候选 | B |
| Step06 Hole Setup / Bolt Connectors | S06-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step06-development\dist\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | 用户指定目录 | **用户已明确指定** | **A** |
| Step06 hoop-cut | S06-B | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step06-development\dist\hoop-cut\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `...\hoop-cut\CADtoCAE_Step06_HoleSetup` | 其他版本；保留 | B |
| Step06 hoop-post-validation | S06-C | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step06-development\dist\hoop-post-validation\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `...\hoop-post-validation\CADtoCAE_Step06_HoleSetup` | 其他版本；保留 | B |
| Step06 identity-fix | S06-D | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step06-development\dist\identity-fix\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `...\identity-fix\CADtoCAE_Step06_HoleSetup` | 其他版本；保留 | B |
| Step07 V3 D1 专项荷载 | S07-A | `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Dist\CADtoCAE_Step07_V3_D1_Luan\CADtoCAE_Step07_V3_D1_Luan.exe` | 用户提供路径 | **用户提供的最新版路径；待最终确认** | **A** |
| Step07 V3 D1 1.1 / 0.70 变体 | S07-B | `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Dist\CADtoCAE_Step07_V3_D1_Luan_1_1\CADtoCAE_Step07_V3_D1_Luan_1_1.exe` | `...\CADtoCAE_Step07_V3_D1_Luan_1_1` | 其他独立候选；不得替换 S07-A | **A** |
| Step07 通用分析设置 + ODB 提取 | S07-C | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development\dist\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe` | `...\CADtoCAE_Step07_AnalysisSetup` | 建议作为不同功能单独保留；待确认 | **A（相对构建快照）** |
| BatchRunner GUI V40 | BAT-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-BatchRunner\dist\CADtoCAE_BatchRunner_V40\CADtoCAE_BatchRunner_V40.exe` | `...\CADtoCAE_BatchRunner_V40` | 建议候选；待确认 | B |
| BatchRunner CLI V40 | BAT-B | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-BatchRunner\dist\CADtoCAE_BatchRunner_CLI_V40\CADtoCAE_BatchRunner_CLI_V40.exe` | `...\CADtoCAE_BatchRunner_CLI_V40` | 建议与 GUI 成对确认 | B |
| ODB 结果提取 | ODB-N/A | 未发现独立 ODB EXE | 由 S07-C 生成提取脚本/运行记录 | S07-C 的独立功能入口，不是另一个产品 EXE | A/B 随 S07-C 快照与生成结果 |
| 支架选型工具 | SEL-A | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Selection-V1\dist\PV_Support_Selection_V1.0_Unified\PV_Support_Selection_V1.0.exe` | `...\PV_Support_Selection_V1.0_Unified` | 相关后续工具候选；待确认是否纳入 | B |

## 3. 全部候选包明细

包大小为运行包目录内全部文件的递归总和；它不是磁盘占用空间。主 EXE 以外的 `_internal`、DLL 等只作为依赖，不另算独立产品。

### 3.1 Step01

| 编号 | 用途 | SHA-256 | 修改时间 | EXE / 包大小 | 依赖与记录 | 状态 |
|---|---|---|---|---|---|---|
| S01-A | 材料表截图 OCR、生成材料/零件数据 | `0F1100C487141CFB006CB6AA9D254F13616A085947EDB9DE9BDF261D658B85B1` | 2026-09-01 16:53:10 | 7,019,953 / 273,676,449 B；1,787 文件 | `_internal`、RapidOCR、ONNX Runtime、openpyxl、config、log；入口 `scripts\step01_pdf_material_gui.py` | 建议候选；B |

证据：工作区 clean，提交 `46701622d54d8f4d53af40bf0e9c60e420f26e21`（`feat(step01): improve material table OCR and component naming`）；有 `.spec` 和 `scripts\build_step01_exe.ps1`。未找到精确源码哈希清单，故不提升为 A。OCR 数量/长度 hotfix 工作区 clean，但未发现它另行产出的 Step01 EXE。

### 3.2 Step02

| 编号 | 用途 | EXE / 运行包目录 | SHA-256 | 修改时间 | EXE / 包大小 | 版本/依赖/记录 | 状态 |
|---|---|---|---|---|---|---|---|
| S02-A | 修正 HOOP 内外轮廓、过渡半径和 Tcl/Tk 打包 | `...\CADtoCAE-fix-step02-hoop-inner-profile\dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe` | `260D2F5D38830DC3C7D05EC0CCB02BFF409673C00F1E507C119B22AE352D4B95` | 2026-09-29 15:06:24 | 6,042,132 / 71,578,014 B；1,240 文件 | `_internal`、Tcl/Tk、openpyxl、config；PR #8 工作区 | 建议候选；B |
| S02-B | Tcl/Tk 专项替代包 | `...\dist\CADtoCAE_Step02_PartScript_TkFix\CADtoCAE_Step02_PartScript_TkFix.exe` | `11A8EE568183A65355898A03288E0E013897DEE01BAAA8E830DA9350C96282C3` | 2026-09-29 15:27:25 | 2,733,341 / 31,948,133 B；1,190 文件 | `_internal`、Tcl/Tk；名称表明专项修复，不能仅凭时间替换 S02-A | 其他候选；B |
| S02-C | 较早零件脚本包 | `...\CADtoCAE-feature-step2-part-abaqus\dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe` | `51BC23DADD1FFA94AAFF28E47E699E353C3A12D45DF4C450BF5DEB56C021E7CC` | 2026-09-22 19:14:35 | 2,733,039 / 31,919,649 B；1,189 文件 | PR #8 前来源；clean 工作区提交 `c3f68d4` | 其他候选；B |

S02-A 所在工作区 clean，提交 `cdf583663c3aeb0a6fcdacb67f99caff1e05056a`；构建脚本显式探测并打包 Tcl/Tk，复制 Step02 使用说明。没有精确 EXE—源码哈希清单。

### 3.3 Step03

未发现独立 Step03 产品 EXE。发现的实现是：

- `scripts\step03_generate_coordinate_workbooks.py`
- `src\cadtocae\coordinate_workbooks.py`
- `CADtoCAE-EXE-Testing\step03` 中的坐标工作簿、装配脚本、汇总和分析产物

判断：这是供 Step04 消费的坐标工作簿生成工作流；测试目录是使用/输出证据，不是完整产品运行包。如果原本应有人工验证过的 Step03 EXE，需要用户补充其路径。

### 3.4 Step04

| 编号 | 用途 | EXE | SHA-256 | 修改时间 | EXE / 包大小 | 依赖与记录 | 状态 |
|---|---|---|---|---|---|---|---|
| S04-A | SP_SC、SP_DC、DP、文件夹发现、多项目 GUI | `...\CADtoCAE-feature-step04-dp-assembly\dist\CADtoCAE_Step04_AssemblyScript\CADtoCAE_Step04_AssemblyScript.exe` | `9C89663D72BD14257BBA03A7F2C362A9F735FA6C21132768CCD0A2A309D4C99E` | 2026-09-29 10:25:16 | 6,156,016 / 74,919,360 B；1,243 文件 | `_internal`、openpyxl、config、Step04_usage；clean 提交 `a4ead2b` | 建议候选；B |
| S04-B | 较早 SP_SC/SP_DC 装配脚本 | `...\CADtoCAE-feature-step04-development\dist\CADtoCAE_Step04_AssemblyScript\CADtoCAE_Step04_AssemblyScript.exe` | `EF20241565819E8E8E6E929A0691C1D2F78E90E10441C3ED4C9471E719CB7C0F` | 2026-09-26 09:28:28 | 2,801,562 / 31,987,933 B；1,189 文件 | `_internal`、openpyxl；clean 提交 `e906b6b` | 其他候选；B |

S04-A 有 `.spec`、`scripts\build_step04_exe.ps1`，入口 `scripts\step04_assembly_script_gui.py`。它的功能证据比 S04-B 完整，但没有精确源码哈希清单。

### 3.5 Step05

| 编号 | 用途 | EXE | SHA-256 | 修改时间 | EXE / 包大小 | 依赖与记录 | 状态 |
|---|---|---|---|---|---|---|---|
| S05-A | 主分析设置 GUI | `...\dist\CADtoCAE_Step05_AnalysisSetup\CADtoCAE_Step05_AnalysisSetup.exe` | `11A92D27A6BF7482636D74200F58119C5B4FCADC1C2A595044461522A870CBE2` | 2026-10-16 11:57:40 | 6,244,030 / 75,156,586 B；1,254 文件 | `_internal`、Tcl/Tk、openpyxl、config、10 个明文 runtime 模块、Step05_usage | 建议候选；B |
| S05-B | 批量诊断 | `...\dist\Step05_BatchDiag\Step05_BatchDiag.exe` | `ECA55681932E69A08283CAECC1D5D1252F92AA01527FB472D0ACFFED243C73D7` | 2026-09-28 08:50:30 | 6,208,888 / 75,102,024 B；1,251 文件 | 专项诊断入口；不应与主程序合并理解 | 辅助候选；B |
| S05-C | 单文件夹旧候选 | `...\dist\step05_single_folder\CADtoCAE_Step05_AnalysisSetup\CADtoCAE_Step05_AnalysisSetup.exe` | `0F9DC9D5E479D5FEBF695426CA1C4C6BB4724028C96748270FA05D5A1A16027C` | 2026-09-28 10:05:04 | 6,207,238 / 75,102,715 B；1,252 文件 | 单文件夹布局 | 其他候选；B |

S05-A 包内 10 个明文 runtime 文件与当前工作区对应文件哈希一致，但 GUI/生成器全体没有精确快照；现有 `source_integrity_proof.json` 指向另一旧 EXE 哈希，并非 S05-A。Step05 工作区当前有 18 项修改/未跟踪内容，故未来备份不能只依赖提交号。

### 3.6 Step06（用户已指定）

| 编号 | 用途 | EXE | SHA-256 | 修改时间 | EXE / 包大小 | 版本/记录 | 状态 |
|---|---|---|---|---|---|---|---|
| S06-A | Hole Setup / Bolt Connectors 主发布包 | `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-feature-step06-development\dist\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `016421FAFAA08B3D6FF3BCE44452304976BDFAB0DED33BC0C813D8DBCE82E653` | 2026-11-01 20:37:11 | 6,280,699 / 72,476,698 B；1,259 文件 | 版本 `0.2.14`；release + smoke 均 SUCCESS | **用户已明确指定；A** |
| S06-B | hoop-cut | `...\dist\hoop-cut\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `F01D269D5E54CE7E57971A6C27CC13011F5A03A1959B2875EC5B84C6D6122829` | 2026-10-10 16:57:56 | 6,217,544 / 75,111,869 B；1,250 文件 | HOOP cut 专项阶段 | 其他版本；B |
| S06-C | hoop-post-validation | `...\dist\hoop-post-validation\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `F01D269D5E54CE7E57971A6C27CC13011F5A03A1959B2875EC5B84C6D6122829` | 2026-10-10 17:10:09 | 6,217,544 / 75,117,087 B；1,250 文件 | 主 EXE 与 S06-B 相同，但包内容总大小不同，不能只按 EXE 哈希删除其一 | 其他版本；B |
| S06-D | identity-fix | `...\dist\identity-fix\CADtoCAE_Step06_HoleSetup\CADtoCAE_Step06_HoleSetup.exe` | `5598C8BBE1888653373773D58CF1E6426797ADD2724B51E3C24DE1152ECDA27F` | 2026-10-10 12:00:21 | 6,217,333 / 75,096,138 B；1,249 文件 | identity 专项阶段 | 其他版本；B |

S06-A 目录存在。顶层含主 EXE、`_internal`、`log`、`Step06_usage.md`；`_internal` 约 66.17 MB / 1,257 文件，包含 Tcl/Tk、openpyxl、配置及 Step06 runtime 模块。精确证据：

- `build\step06-release-20261101-203643-b24f21fb\release.json`：版本 `0.2.14`，状态 `SUCCESS`，记录该发布 EXE 路径。
- 同构建目录 `smoke.json`：状态 `SUCCESS`。
- 构建暂存 EXE 与发布 EXE SHA-256 完全相同。
- 构建入口 `scripts\build_step06_exe.ps1`；GUI 入口 `scripts\step06_hole_setup_gui.py`。

注意：Step06 工作区当前有 97 项未跟踪内容，HEAD 为 `ff322e1`。A 级对应依赖发布记录和构建快照，不表示仅靠该 Git 提交即可重建全部当前源码。

### 3.7 Step07：功能分组

#### 3.7.1 V3 D1 独立专项程序

| 编号 | 用途 | EXE | SHA-256 | 修改时间 | EXE / 包大小 | 构建证据 | 状态 |
|---|---|---|---|---|---|---|---|
| S07-A | V3 D1 Luan 专项荷载程序 | `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Dist\CADtoCAE_Step07_V3_D1_Luan\CADtoCAE_Step07_V3_D1_Luan.exe` | `1D2D401BD24BC0F6D2260147B82FA79B091F7B3D5988BD0E3AC10D181DC21F96` | 2026-11-12 10:33:29 | 6,034,930 / 71,365,408 B；1,058 文件 | `build_manifest.json` 版本 `V3-D1-1.0`，108 个源码哈希；`Test_Results\exe_smoke.json` SUCCESS | **用户提供的最新版路径；A；待最终确认** |
| S07-B | V3 D1 1.1 / 总体荷载 0.70 变体 | `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Dist\CADtoCAE_Step07_V3_D1_Luan_1_1\CADtoCAE_Step07_V3_D1_Luan_1_1.exe` | `FD7D30A989FBDB1CDF02E0109A657DD31F608121DDBD28DF9A2DDD6884351B8E` | 2026-11-12 11:53:30 | 6,035,759 / 71,366,748 B；1,058 文件 | `build_manifest_1_1.json` 版本 `V3-D1-1.1`，108 个源码哈希；overall070 冒烟 SUCCESS | 其他独立候选；A |

S07-A 的当前 `Source\Step07` 有 3 个文件已经发生后续变化，但 `Original_Baseline\V3_1_0_before_all_factor` 中存在与 1.0 清单哈希一致的旧源码，包内 runtime 也能对应，因此仍评为 A。S07-B 的 1.1 清单与当前隔离源码快照全部对应。不能因 1.1 的数字或时间较新而自动替换用户提供的 S07-A。

#### 3.7.2 通用 Step07 AnalysisSetup / ODB

| 编号 | 用途 | EXE / 目录 | SHA-256 | 修改时间 | EXE / 包大小 | 状态 |
|---|---|---|---|---|---|---|
| S07-C | 阶段 01—06 分析设置 + 阶段 07 ODB 提取 | `...\CADtoCAE-Step07-Development\dist\CADtoCAE_Step07_AnalysisSetup\CADtoCAE_Step07_AnalysisSetup.exe` | `C8CE1BA6D0A7083240909072D1387E1A60F3C37446A4514109DA027B0CB2CD0B` | 2026-11-03 13:51:38 | 6,091,342 / 71,435,660 B；1,060 文件 | 建议按不同功能单独保留；A（相对 manifest 快照） |
| S07-D | Chinese 0.9.1 候选 | `...\dist\CADtoCAE_Step07_Chinese_091\CADtoCAE_Step07_AnalysisSetup.exe` | `94CBE7FB3697D914D6B52518F8CAADC3186B5151E3950AB84FB25203513E8BE6` | 2026-11-03 11:58:33 | 6,091,341 / 71,427,387 B；1,060 文件 | 其他候选；B |
| S07-E | 0.8.3 staging 候选 | `...\dist\Step07_083_Staging\CADtoCAE_Step07_AnalysisSetup.exe` | `5914589A54401F02C5C626E79C66AD0B1DDC41D51072D33581998B1E2BAB9687` | 2026-11-01 22:33:10 | 6,070,094 / 71,375,154 B；1,058 文件 | 其他候选；B |

S07-C 包内有 `build_manifest.json`、Step07 使用说明和 ODB 使用说明。清单记录基线 `ff322e1fda786378aa17f5f31690d280537c9928`、分支 `feature/step07-analysis-setup` 和 34 个源码哈希。当前 Step07 工作区已有 162 项未跟踪/变更；其中两个 runtime 与 manifest 不同，但 manifest 对应版本可在包内/快照中找到。因此 A 只针对构建清单所定义的快照，不表示当前脏工作区整体等同于 EXE。

#### 3.7.3 通用 Step07 历史/专项包

以下均是 `CADtoCAE_Step07_AnalysisSetup.exe` 产品家族的历史或专项阶段，不是 `_internal` 依赖。路径基准为 `F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-Step07-Development`。

| 编号 | 相对运行包目录 | SHA-256 | 修改时间 | EXE / 包大小（B） | 状态/源码对应 |
|---|---|---|---|---|---|
| S07-H01 | `dist\Archive\CADtoCAE_Step07_080_before_bc_fix` | `5ADBC574375B10C1C4A40119D09E7CC34700FB5116872C712BB3195B6F1D4C3B` | 2026-11-01 21:45:31 | 6,070,086 / 71,373,454 | 历史包；B |
| S07-H02 | `dist\Archive\CADtoCAE_Step07_081_before_solid_coarsening` | `0D52F6EB9113FA004C552A789442DEE40F1174FE1623B2FB9F12176A2065A237` | 2026-11-01 22:07:00 | 6,070,085 / 71,373,844 | 历史包；B |
| S07-H03 | `dist\Archive\CADtoCAE_Step07_AnalysisSetup_legacy_032` | `3EDB1A8F7A7A2E74F83D2659C5179B5353AB2D29B5FD9E32C0BCB538206C93DE` | 2026-10-17 10:08:31 | 1,923,052 / 28,478,609 | legacy；B |
| S07-H04 | `dist\Archive\CADtoCAE_Step07_DualCases_073` | `D1BD5F7773EABC7F607BE7245305464F5127B233B178677613AD1357790D718E` | 2026-10-20 08:20:19 | 6,061,627 / 74,148,044 | DualCases 专项；B |
| S07-H05 | `dist\Archive\CADtoCAE_Step07_InPlace_070` | `482F896FBA2A993E91D3FD71B86072BBF317AE285899C5D5542E521C26514D0F` | 2026-10-20 03:54:16 | 1,958,537 / 28,654,888 | InPlace 专项；B |
| S07-H06 | `dist\Archive\CADtoCAE_Step07_Load_J13_071` | `A488F0DF4DC204BD61DF590D5D47F7F17D987D3EC32C6DF393265B5D56507EBE` | 2026-10-20 04:34:00 | 6,056,527 / 74,142,857 | Load J13 专项；B |
| S07-H07 | `dist\Archive\CADtoCAE_Step07_Pipeline_060` | `2341A199335EA0D24B34128E9AA50909BDFF0FA5F87038E33BA3FC8B4EE3EA28` | 2026-10-19 10:08:30 | 1,951,264 / 28,619,989 | Pipeline 专项；B |
| S07-H08 | `dist\Archive\CADtoCAE_Step07_Pipeline_061` | `D74F6DFEF9F7ADA38F12EAC25D688F2E1575BE3B0153E08D78D7988F2B386ECA` | 2026-10-19 11:23:26 | 1,953,421 / 28,630,751 | Pipeline 专项；B |
| S07-H09 | `dist\Archive\CADtoCAE_Step07_Quality_062` | `7746E1697D0491CB3D8ADBC42E26A1548FB1A7EAE0345D3E59CA2C8489E0062D` | 2026-10-19 11:40:05 | 1,953,428 / 28,636,810 | Quality 专项；B |
| S07-H10 | `dist\Archive\CADtoCAE_Step07_SourceGuard_063` | `02CEB0DA22DF2B0961A9F03CE10C0BE8DD6C04B370A3F0430259DA358B7FD98C` | 2026-10-20 03:23:29 | 1,953,893 / 28,642,048 | SourceGuard 专项；B |
| S07-H11 | `dist\Archive\CADtoCAE_Step07_Tributary_072` | `BB7A4A86EB0B47ECA59C5672BF18699AC90B02CD4607D819D105A67A0E7CB861` | 2026-10-20 05:21:15 | 6,060,642 / 74,150,757 | Tributary 专项；B |
| S07-H12 | `dist\Archive\V0.3.3\CADtoCAE_Step07_AnalysisSetup` | `076CF3AC533FE1A2D5FAC07FAD1B1DC5960BCB62ED888B9A64FED4675495AFE1` | 2026-10-17 10:19:44 | 1,925,595 / 28,483,130 | 历史版本；B |
| S07-H13 | `dist\Archive\V0.3.4\CADtoCAE_Step07_AnalysisSetup` | `AA76C759898401C438338FB3F7066FCB08F26D1BE7E74090A907E3E7F2F71777` | 2026-10-17 11:05:37 | 1,926,113 / 28,491,429 | 历史版本；B |
| S07-H14 | `dist\Archive\V0.3.5\CADtoCAE_Step07_AnalysisSetup` | `ADCE601EDFF0F91BECFC369722382EEA556D63A6E31DB3EE06218A7AB5D3E723` | 2026-10-17 11:14:36 | 1,926,401 / 28,494,135 | 历史版本；B |
| S07-H15 | `dist\Archive\V0.5.0\CADtoCAE_Step07_AnalysisSetup` | `17A5DED5B439A92242ED3F9E90198A6486D97157EAEBAE27E5ADF5B18F4AA37E` | 2026-10-18 09:18:39 | 1,937,092 / 28,531,899 | 历史版本；B |
| S07-H16 | `dist\Archive\V0.5.1\CADtoCAE_Step07_AnalysisSetup` | `58DFC3926CEAE11888DF7D48AA32CE0306F9E5CE8B1865C1BB30BB9F89CD95E0` | 2026-10-18 15:08:51 | 1,938,217 / 28,543,031 | 历史版本；B |
| S07-H17 | `dist\Archive\V0.5.2\CADtoCAE_Step07_AnalysisSetup` | `50838FDC2F15A4890573FD9252C0386E209DD5DD4ABA1982C4795037B390FFAE` | 2026-10-18 15:51:51 | 1,938,245 / 28,546,509 | 历史版本；B |
| S07-H18 | `step07_runs\backups\before_folder_batch_20261016\previous_exe` | `A14234F539D5363F32AE955E58E018C89CEB705369D3A5D3FD9ACAFD7A375267` | 2026-10-16 16:10:17 | 1,917,721 / 28,465,985 | 备份包；B |

隔离目录 `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Source\Step07` 还保存了上述通用 Step07 源码/运行包的镜像副本，关键 EXE 哈希和包大小一致。它们是物理上的第二份副本，不另编号为新的产品版本；第二阶段备份时应说明镜像关系，避免误判为新版本。

### 3.8 CADtoCAE-BatchRunner

| 编号 | 程序 | SHA-256 | 修改时间 | EXE / 包大小（B） | 状态 |
|---|---|---|---|---|---|
| BAT-A | GUI V40 | `0B75E5707A7CD78E97B4926EBFF765496C009E08D8F41F3CB8276B3314F7D18D` | 2026-10-20 07:57:44 | 1,978,972 / 28,537,799 | 建议 GUI 候选；B |
| BAT-B | CLI V40 | `A1899CFF1E37656ADA9330AAF8C79EBE4B49F48C4405B3D0B212F668E267A5FD` | 2026-10-20 07:58:08 | 1,823,620 / 20,714,787 | 建议 CLI 候选；B |
| BAT-C | GUI V32 | `45C449062A7B34DDDA916CF344165F7B639D5A44AAC8A45CA71C016B48E7385D` | 2026-10-17 11:07:41 | 1,973,940 / 28,527,297 | 其他候选；B |
| BAT-D | CLI V32 | `4051E5E503EA70A74F325613C0FE0905CA286AA0C291F351E0213736C3DBF563` | 2026-10-17 11:07:58 | 1,819,079 / 20,702,373 | 其他候选；B |
| BAT-E | GUI V31 | `5B8BBC33BC827D7CDD9412B5D2D0CFC4740D6614144743946337BE0CDEEAB3FF` | 2026-10-11 09:37:55 | 1,968,880 / 28,507,386 | 其他候选；B |
| BAT-F | CLI V31 | `301301E2EFBB0211C365FD97051AE84622C1263DBE119395BE6D720E6AD6726D` | 2026-10-11 09:38:17 | 1,814,946 / 20,681,022 | 其他候选；B |
| BAT-G | GUI 基础名 | `94E043219EC7F394C5EBEFAF68E7662F6C34D31EEAA70606F1F00D5186E8B537` | 2026-10-11 09:12:04 | 1,954,531 / 28,493,646 | 其他候选；B |
| BAT-H | CLI 基础名 | `9966CA02E910058AB51D9264A9EAAC8C8AFA1C8383233F20B9060D39D8708DD1` | 2026-10-11 09:12:26 | 1,802,360 / 20,668,436 | 其他候选；B |

源码入口为 `scripts\batch_runner_gui.py` 和 `scripts\batch_runner.py`；有 `scripts\build_batch_runner_exe.ps1`、8 个 `.spec`、V31/V32/V4 验证文档。工作区当前有 27 个未跟踪文件，未发现精确 EXE—源码哈希清单，因此为 B。GUI 与 CLI 是不同入口，应分别确认，不应只保留一个而默认另一个可替代。

### 3.9 支架选型后续工具

| 编号 | 程序包 | SHA-256 | 修改时间 | EXE / 包大小（B） | 状态 |
|---|---|---|---|---|---|
| SEL-A | Unified | `482BCFDD0E824CC188179176421578414D55AFEC1DC455A0FD4C8EC23BFBF40B` | 2026-10-20 09:07:29 | 30,946,076 / 31,309,609 | 相关工具建议候选；B |
| SEL-B | Span | `67CD50086EE4444B39D2C62F43C74D2ED89CB95C0EEF5D1DB2EF100041FADFD6` | 2026-10-20 10:34:11 | 31,014,748 / 31,271,602 | 其他功能候选；B |
| SEL-C | ExcelResults | `35A0203C86553016C6A3288A70B34BA8C56A0DF7F358BD656D95EB428A213DD7` | 2026-10-20 08:52:59 | 30,935,788 / 31,288,449 | 其他功能候选；B |
| SEL-D | 基础 V1.0 | `AEEF8AAE44BF7B42381174178FB6884985DBAB6CC10E643A4D3AF0D2BB1207ED` | 2026-10-20 08:29:29 | 30,868,521 / 30,999,672 | 其他候选；B |

这些是一文件 EXE 加少量配置/数据/资产的包，有 `selection_software\scripts\build.ps1`、多份验证文档和 smoke JSON。工作区有 39 项修改/未跟踪内容，没有精确源码 manifest，故均为 B。是否纳入后续 CADtoCAE 最终备份需用户确认。

## 4. Step07 程序的功能和依赖关系

1. **S07-A / S07-B：V3 D1 专项荷载程序**  
   面向隔离的 V3 D1 / Luan 荷载工作流，生成相应脚本或输入。S07-B 的现有说明指向总体荷载因子 0.70。两者有各自清单与 smoke 记录，是同一专项家族的两个明确构建，不应仅按数字大小自动取代。

2. **S07-C：通用 AnalysisSetup + ODB 后处理入口**  
   覆盖分析设置阶段，并提供 ODB 结果提取阶段。ODB 提取并非另一个独立 EXE；程序生成/调度 Python 脚本，实际读取 ODB 时仍依赖 Abaqus/CAE 2020 环境、ODB 文件和 `assembly_summary.json` 等项目产物。

3. **S07-D / S07-E / S07-Hxx：同一通用产品家族的不同阶段**  
   Chinese、staging、Pipeline、Quality、SourceGuard、InPlace、Load、Tributary、DualCases 等是历史或专项验证阶段。它们不是 18 个互不相关的最终产品，但因功能演化和人工验证线索不同，本阶段全部保留记录。

4. **`CADtoCAE-EXE-Testing`**  
   未发现产品 EXE；其中是实际使用结果、脚本、ODB 提取结果、验收/验证记录。它应作为验证证据和项目样本备份，而不能替代完整运行包。

5. **`Report-Generation` 与 `outputs`**  
   没有发现需另列的产品 EXE；它们是报告/诊断工作区和产物目录。

## 5. 建议保留的候选及依据

以下仅是备份候选建议，最终选择仍需用户确认：

- **S01-A**：扫描范围内唯一完整 Step01 产品包；有 clean 源码工作区、构建脚本和功能提交。
- **S02-A**：明确对应 PR #8 的 HOOP 几何修正和 Tcl/Tk 运行时打包；S02-B/S02-C 继续作为其他版本保留。
- **S04-A**：有 DP、文件夹发现和多项目 GUI 的功能证据；S04-B 是较早基线。
- **S05-A**：主产品入口，包内 runtime 与当前对应文件一致；但源码对应仍为 B，后续备份必须连同未提交内容和证据保存。
- **S06-A**：严格遵从用户已指定目录；有精确 release/smoke 证据，其他三个目录不替换它。
- **S07-A**：严格按用户新提供的最新版路径进入待确认清单；不因 S07-B 名称为 1.1 而替换。
- **S07-C**：建议作为与 V3 D1 专项不同的“通用分析设置 + ODB”工具单独保留；它不是 S07-A 的简单旧版。
- **BAT-A + BAT-B**：如果需要 BatchRunner，建议 GUI/CLI 成对确认；依据是 V4 功能验证记录，不仅是时间较新。
- **SEL-A**：仅当选型工具属于最终仓库范围时考虑；Span、ExcelResults 可能代表独立业务差异，需用户判断。

## 6. 对应源码和构建方式清单

| 产品 | 开发/源码位置 | 主要入口 | 构建依据 | 对应结论 |
|---|---|---|---|---|
| Step01 | `CADtoCAE-feature-step01-development` | `scripts\step01_pdf_material_gui.py`；`src\cadtocae\material_pdf.py` / `pdf_tables.py` | `CADtoCAE_Step01_MaterialTable.spec`；`scripts\build_step01_exe.ps1` | B |
| Step02 | `CADtoCAE-fix-step02-hoop-inner-profile` | `scripts\step02_part_script_gui.py`；`src\cadtocae\part_script.py` | `scripts\build_step02_exe.ps1`；Tcl/Tk 探测脚本；PR #8 文档/tests | B |
| Step03 | main/各功能工作区 | `scripts\step03_generate_coordinate_workbooks.py`；`src\cadtocae\coordinate_workbooks.py` | 脚本工作流，无独立 EXE 构建依据 | — |
| Step04 | `CADtoCAE-feature-step04-dp-assembly` | `scripts\step04_assembly_script_gui.py`；装配 plan/executor 模块 | `CADtoCAE_Step04_AssemblyScript.spec`；`scripts\build_step04_exe.ps1`；使用说明 | B |
| Step05 | `CADtoCAE-feature-step05-development` | `scripts\step05_analysis_script_gui.py`；多个 `*runtime.py` | `CADtoCAE_Step05_AnalysisSetup.spec`；`scripts\build_step05_exe.ps1` | B；10 个 runtime 精确匹配，但整体未证实 |
| Step06 | `CADtoCAE-feature-step06-development` | `scripts\step06_hole_setup_gui.py`；hole/connector runtime | `scripts\build_step06_exe.ps1`；release.json；smoke.json；包内 usage | A（指定发布包） |
| Step07 通用 | `CADtoCAE-Step07-Development` | `scripts\step07_analysis_setup_gui.py`；`step07_*` 模块 | `scripts\build_step07_exe.ps1`；包内 `build_manifest.json`；usage/ODB usage | A（manifest 快照）；当前工作树不是同一整体状态 |
| Step07 V3 D1 | `F:\Codex\PV_Wind_Load_Feasibility\Step07_V3_D1_Isolated\Source\Step07` 及 baseline 快照 | V3 load / pipeline desktop/runtime 模块 | `Dist\build_manifest.json`、`build_manifest_1_1.json`；smoke JSON | S07-A/S07-B 均 A |
| BatchRunner | `CADtoCAE-BatchRunner` | `scripts\batch_runner_gui.py`；`scripts\batch_runner.py` | `scripts\build_batch_runner_exe.ps1`；8 个 spec；V31/V32/V4 验证文档 | B |
| Selection | `CADtoCAE-Selection-V1\selection_software` | selection software 入口 | `selection_software\scripts\build.ps1`；validation/smoke 记录 | B |
| ODB 提取 | Step07 通用源码/生成脚本 | `step07_postprocess*` 与 ODB 使用流程 | S07-C manifest、EXE-Testing 的实际结果记录 | 不是独立 EXE；随 S07-C 及项目结果备份 |

## 7. 需要用户判断的具体事项

1. 是否正式确认 **S07-A** 为 Step07 V3 D1 最终主运行包？本报告已按用户提供路径优先列出，但仍保留确认步骤。
2. **S07-B（1.1 / overall070）** 是应与 S07-A 同时保留的独立业务变体，还是仅作为其他历史候选？
3. **S07-C 通用 AnalysisSetup + ODB** 是否作为与 V3 D1 专项并列的第二个 Step07 最终程序保留？从功能证据看，建议并列，而不是二选一。
4. 是否确认 S01-A、S02-A、S04-A、S05-A 为各步骤主运行包？
5. Step03 没有发现独立 EXE：这是否符合人工验证实际，还是另有未在扫描位置中的 Step03 EXE？
6. BatchRunner 是否确认同时保留 BAT-A（GUI V40）和 BAT-B（CLI V40）？
7. Selection 工具是否属于后续目标仓库范围；若属于，Unified、Span、ExcelResults 是否都是独立需要保留的功能？
8. 第二阶段是否需要把 Step07 的全部历史/专项包连同镜像副本一起归档，还是只归档经确认的最终包、构建快照和验证记录？本阶段未删除或移动任何版本。

用户确认 EXE/运行包后，源码对应状态仍保持本报告的 A/B/C 证据等级；不会因为“确认 EXE”而自动把 B/C 改成 A。

## 8. 当前工作区风险提示（供第二阶段使用）

- main 工作区 clean，未被本次盘点修改。
- Step05、Step06、Step07、BatchRunner、Selection 等开发目录含未提交或未跟踪内容；第二阶段备份时必须把“Git 已提交内容”和“当前源码快照”分开处理。
- 本阶段没有做反编译、重构、重打包或功能复测。
- 没有删除、移动、覆盖任何原包，也没有创建 Git 分支、提交、标签或远程操作。

