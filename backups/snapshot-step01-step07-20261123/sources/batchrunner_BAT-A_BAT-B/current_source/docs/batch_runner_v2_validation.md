# BatchRunner V2 交付与验证

日期：2026-10-11。Worktree：CADtoCAE-BatchRunner；分支 feature/batch-runner。
保留既有 V1 实现，未 commit/push，未修改 main 或其他开发 worktree。

## 根因与修复

原批次 20261011-083533-6e8a5ea3 的 Hole 第 786 行出现 RemoveFaces AttributeError。
最初仅据异常提出脚本/API 兼容性可能性，随后通过同一 CAE 副本的只读探测推翻：
导入 part 前 9 个 Part 都没有 RemoveFaces；导入后全部具备该方法。
真实根因是 BatchRunner noGUI 包装器缺少标准 CAE 模块初始化，修复仅在 cae_worker.py。
Hole/Connector 的几何算法和原始 PY 均未修改。
详见 batch_runner_v2_diagnosis.md、outputs/v2-api-probe/api_probe.json。

## 交付功能与文件

- matching.py：确定性合法目录查找、静态读取解析、JSON 身份/XLSX 容器校验、读取/存在判断绑定。
- dependencies.py / scanner.py：文件清单、内嵌与外部输入区分、READY/MISSING_INPUT、等待上游及可选来源冲突。
- preflight.py：只读校验历史指纹、上游链及 CAE/artifacts，分开展示本次就绪和历史 SUCCESS/STALE/FAILED。
- executor.py：输入快照哈希核对、input_bindings.json、运行副本路径绑定、原始异常直接展示。
- runner.py / cli.py：默认 smart、默认 root/.batchrunner、继续保留 full/resume/from 和命令行。
- gui.py / settings.py：选目录自动扫描、一键开始、阶段详情树、错误详情、折叠高级设置、有效启动器偏好。
- cae_worker.py：修复 noGUI API 初始化。
- tests/test_batch_runner_v2.py：18 项新增测试；原测试适配 MISSING_INPUT 状态。
- scripts/validate_batch_runner_v2_inputs.py：在实际文件副本上生成预检查矩阵。
- scripts/validate_batch_runner_in_abaqus.py：增加绝对外部 JSON 路径绑定的真实 Abaqus 冒烟。
- docs/batch_runner_usage.md：V2 使用说明；原 V1 validation 文档保留为历史记录。

## 自动化结果

全仓库运行 209 项：208 通过、1 跳过、0 失败。
跳过原有 test_step01_pdf_only_does_not_fake_components，原因 sample PDF is not available。
BatchRunner 专项共 50 项通过，其中 V2 新增 18 项。
日志：outputs/v2_regression_final.log、outputs/v2_tests.log。

覆盖：自动读取路径绑定、绝对/相对/变量/组合路径、读取与存在判断同向绑定、JSON/Excel 缺失、
JSON 身份错误、准确候选冲突、可选输入、内嵌计划不误依赖外部文件、历史报告拒用、
上游等待、智能复用及下游失效、9 项目串行、部分项目、GUI 自动扫描/隐藏高级设置、启动器偏好。

## 实际项目验证

源目录：F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-EXE-Testing/step06test2。
项目：SP_SC_ANG18_11042210101041S-T0202。

1. 原始失败批次：前三步 CAE 和 artifacts 哈希重新核对有效，Step5 未执行。
2. 修复前重现：20261011-084758-4ba10f68，仅重跑 Step4，前三步 reused，稳定重现 API 错误。
3. 修复后：20261011-085234-b228d76d，五步全部 SUCCESS；包装器变化使旧链保守失效，
   在新批次重新建模。每阶段都通过模型/报告校验、CAE 保存及重新打开。
4. 再次一键智能运行：20261011-085339-27ea0c2a，五步全部 reused，不重复创建模型对象。
5. Connector 实际报告：step06_total_connectors=8、step05_regression_status=PASS、errors=[]。
6. Step5 的 input_bindings.json 明确指向同批次 Step4/runtime_report.json，未使用原目录旧报告。
7. 原目录全部原始 PY/JSON/Excel/报告 SHA256 未变化；V1 原始三个 CAE 哈希仍一致。

记录分别在源目录 .batchrunner/<批次>/ 下。整个流程没有手选阶段 JSON，也没有提供调度器配置 JSON。

## 输入变体矩阵与额外真实冒烟

outputs/v2-real-input-matrix/a8fed35f/matrix.json：实际文件的独立副本，共 8 个预检查变体通过：
全部齐全、只留前三步、Hole 必需 JSON 缺失、Connector 必需 JSON 缺失、错项目、重复候选、
绝对路径迁移、内嵌脚本缺少可选计划 JSON。

当前标准 Hole/Connector 已内嵌计划，不原生依赖外部计划 JSON。因此“必需计划缺失”等变体
仅在副本中显式添加读取语句来构造真实外部读取契约，且这些改造副本只做静态预检查、不执行几何。
这与错误地把所有旁边的 JSON 都设为必需不同。

outputs/batchrunner-integration/b174380e5b/validation.json：真实 Abaqus 合成三阶段模型，
第 2 步通过被重定向的绝对 JSON 路径读取实例名并创建实例，exists 与 open 同时指向快照；
full、resume、from 3 均通过，含中文与空格路径。它不替代上面的真实五阶段项目验证。

## EXE 与边界

GUI：dist/CADtoCAE_BatchRunner/CADtoCAE_BatchRunner.exe。
CLI：dist/CADtoCAE_BatchRunner_CLI/CADtoCAE_BatchRunner_CLI.exe。
采用 onedir，分发时保留整个目录及 _internal。构建日志 outputs/v2_build_final.log。

未知动态读取、自定义跨目录接口不会猜测；会阻塞并提示需要明确接口。
JSON 身份和 XLSX 完整性检查不是所有工程数据的业务验证。9 项目调度已模拟验证，
本轮真实完整验证是指定目录中的 1 个项目，不能声称其余 8 套支架已验收。
安全停止仍等待阶段保存完成，GUI/模型工程效果仍可由用户人工复核。暂不提交代码。
## 最终打包程序验证

GUI EXE 启动/事件初始化：outputs/v2_gui_exe_smoke.json，PASS，退出码 0，Tk 8.6。
CLI EXE 智能运行：20261011-085608-9e7a075d，五阶段全部复用成功，退出码 0。
CLI EXE 从 Step5 重跑：20261011-085609-1e4fbd8b，前四步 reused，恢复 Step4 CAE 后
重新执行 Connector，五阶段状态均为 SUCCESS，退出码 0。没有在最终模型上叠加连接器。
日志 outputs/v2_exe_resume.log、outputs/v2_exe_from5.log。
最后再次核对原项目文件全部哈希及 V1 旧 CAE，均未覆盖或改变。
