# BatchRunner V2：现状审查与失败诊断

审查时间：2026-10-11。保持 feature/batch-runner / CADtoCAE-BatchRunner。
只读读取 step06test2 的原始 PY、JSON、Excel 及历史批次，不改 Hole/Connector 算法。

## 7 个问题的实证结论

1. GUI 可选配置 JSON 是调度器配置，只读取 command/environment。项目级
   <prefix>_batchrunner.json 是另一种高级阶段契约；都不是 Hole 计划 JSON 选择器。
2. V1 并未通用自动匹配所有运行输入。它识别内嵌 COMPONENTS_JSON、ASSEMBLY_DATA、PLAN；
   固定来源后缀匹配只用于指纹；其他外部输入通常需要 manifest 声明。
3. 来源文件限定同目录、准确 prefix+后缀；脚本按 5 类后缀及 Connector B1 别名识别；
   integrated Connector 的 hole_report_path 改绑到当前项目第 4 步 runtime_report.json。
4. manifest 必需输入缺失和未声明的直接字面量读取会在扫描 BLOCKED；动态表达式读取
   不完整，部分错误只能在 Abaqus 运行中暴露。V1 无独立 MISSING_INPUT。
5. Step4 真正失败是原 Hole PY 第 786 行：
   `feature = part.RemoveFaces(faceList=(inside,))`。
   Abaqus 报 `AttributeError: 'Part' object has no attribute 'RemoveFaces'`。
   调用链：1303 → execute_step06_with_hoop:1237 → execute_step06_a:926 → s6a_shell_cut:786。
   原 PY 与运行副本该行一致；worker_error.txt、stderr.log 和 runtime_report.json 一致。
   不是缺 JSON，也不是匹配到其他项目。进一步的只读 API 探测已确认根因：
   同一份 Step3 CAE 中，在 import part 前全部 9 个 Part 无 RemoveFaces，导入 part 后全部具有该方法。
   因此原先“可能是脚本/API 兼容问题”的初步判断被推翻，实际是 BatchRunner noGUI 初始化缺漏。
   修复仅在 cae_worker.py 初始化标准 CAE 模块，注册 Part/Assembly/Interaction 等 API；不改变开孔算法。
   探测证据：outputs/v2-api-probe/api_probe.json（模型副本只读打开，不保存修改）。
6. Step5 扫描为 PENDING，运行 BLOCKED，原因 Predecessor did not complete in this plan；未执行。
7. 三步 SUCCESS 有本轮 token receipt、模型实体校验、CAE saveAs 后重新打开验证。
   已重新计算现存 CAE 和 artifacts 哈希，全部匹配历史记录：
   Step1 204800 字节，9 Parts/0 Instances；Step2 270336 字节，9/15；Step3 385024 字节，9/15。

证据位置：
`../CADtoCAE-EXE-Testing/step06test2/.batchrunner/20261011-083533-6e8a5ea3/ef80becbd3bd34ac0a4b/`
其中 record.json、step4/worker_error.txt、step4/runtime_report.json 和 step1～3/receipt.json。

## V2 修改计划

- 保留现有调度、保存、恢复模块，新增确定性匹配器：准确项目编号、有限合法目录、候选冲突、
  JSON 身份及 Excel 容器校验、可解析读取表达式与运行副本的精确路径绑定。
- 将实际运行输入与内嵌数据、可选生成来源、上游输出、历史报告分别展示。
- 加入 READY/MISSING_INPUT、等待上游生成、历史 SUCCESS/STALE 与检查点状态。
- 默认 smart（可靠历史续跑），输出 root/.batchrunner；保存有效启动器偏好，高级设置折叠。
- 界面自动扫描，阶段详情树及原始异常详情；保留 CLI、full/resume/from。
- 修复 noGUI 初始化后重新执行实际项目；任何后续业务错误仍保留为 FAILED，不绕过模型校验。

## 已完成的真实修复验证

V2 包装器初始化 part、assembly、interaction、section、material、mesh、sketch、step、load、connectorBehavior。
没有修改测试目录的任何原始 PY、JSON、Excel 或原始报告。

20261011-084758-4ba10f68：修复前再次复用前三步，仅重跑第 4 步，稳定复现 RemoveFaces 异常。
20261011-085234-b228d76d：修复后智能执行，因包装器版本指纹变化安全地重建检查点链，
第 1～5 步全部 SUCCESS。每步保存并重开 CAE，运行报告及 receipt 均经过校验。
实际批次位置：step06test2/.batchrunner/20261011-085234-b228d76d。

因此，本问题最终确认为 BatchRunner noGUI 环境初始化缺漏，并已在调度器内修复。
不是通过更换孔算法、替代 API、读取历史成功报告或忽略异常来获得成功状态。
