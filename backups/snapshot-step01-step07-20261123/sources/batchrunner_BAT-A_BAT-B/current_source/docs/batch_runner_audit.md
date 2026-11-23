# BatchRunner 技术审查与实施方案

基线：main / a0092c0（本地 origin/main 同一提交，未联网 fetch）。
独立分支：feature/batch-runner；独立目录：../CADtoCAE-BatchRunner。
main 干净；已有开发 worktree 保留。Step05/06 来自相邻 feature-step06-development
工作目录的只读审查，包含尚未集成的源码，不能视为 main 已发布接口。

## 真实依赖与接口

| 阶段 | 生成入口 | 生成时输入 | Abaqus 运行时输入 |
|---|---|---|---|
| Part | part_script.py → scripts/make_cae_runner.py | components Excel、standards | 内嵌 COMPONENTS_JSON、MODEL_NAME |
| Assembly | assembly_script.py → main_frame_assembly.py | 坐标 Excel、Part PY/旧版组件 JSON | 内嵌 ASSEMBLY_DATA、同名 Model 中的 Parts |
| Analysis | analysis_batch.py → beam_brace_tie.py / sp_dc_setup.py；早期 analysis_setup.py | assembly_summary JSON、分析输入表及 Part/Assembly 数据 | 内嵌 PLAN、同名已装配 Model；REPORT 为本轮读写报告 |
| Hole | hole_setup.py | 孔表、计划和上游信息 | 内嵌 PLAN、上游 Part/Instance 几何 |
| Connector | step06_release.py → connector_integration.py；早期 connector_setup.py | 孔计划，早期 B1 还需要成功孔报告 | 新版内嵌 PLAN + 第 4 步成功孔报告 + 干净的开孔后 Model |

以上 Excel/JSON 并非一律需要在执行时读取。旧版或用户修改的脚本可能另有外部依赖，
必须显式声明、检查并快照到阶段目录；不跨目录寻找同名文件。

Part 的 create_parts() 捕获单构件异常后继续，退出码零不代表所有 Part 成功；
应捕获其返回的 failed 并检查目标 Parts。Assembly 检查缺失 Parts，并生成几何验证报告；
Analysis/Hole/Connector 有 SUCCESS/FAILED 报告及异常传播。报告路径部分为生成时绝对路径。

Part 默认创建/复用 MODEL_NAME，不自动保存；Assembly 使用已有 mdb.models 并默认不保存；
后三阶段使用传入的 mdb，不自动完成跨进程模型恢复。原始五脚本不能直接独立启动五次。
普通 Python 不能执行这些脚本；原有使用入口是 CAE File → Run Script。
现有 runs.py 管理生成过程，不构成可恢复的五阶段执行记录。

重跑风险：Part 可删除同名 Part；Assembly 有实例/集合复用或覆盖逻辑；开孔显式拒绝既有
STEP06 特征；Connector 要求干净 Step06-A 模型。禁止从最终模型直接重跑中间阶段。
当前发布入口输出 *_step06_connector_setup.py；早期 B1 输出 *_step06_b_connector_setup.py，
后者兼容为第 5 步别名；同时出现两种命名报冲突。不得自动重命名原文件。
新版 integrated PLAN 的 hole_report_path 是运行期真实依赖；包装器将其改为阶段内副本，
仅从本项目有效第 4 步运行记录取得 runtime_report.json。绝不读取原目录中的旧孔报告。
Step05 两类报告变量 REPORT / REPORT_PATH 均在副本重定向。

## 推荐方案 C

每个阶段一个 Abaqus CAE noGUI 包装进程：第 1 步新建数据库，其余步骤打开前一步的
受验证 CAE 副本，执行脚本副本，校验模型和本轮报告，saveAs 到新的唯一阶段目录，再
重新打开验证。所有保存、报告路径重定向仅发生在批次副本，不修改原 PY 或 CAE。
独立命名空间避免上一脚本全局变量泄漏；CAE 是唯一跨阶段模型接口。

检查点有效性由脚本/声明输入/可选生成来源文件 SHA256、上游链、执行器配置和检查点
哈希共同决定。源 Excel 改变即使内嵌脚本未重新生成也保守失效；用户仍须先重新生成脚本。
历史报告存在不算成功。恢复前重新打开 CAE，步骤成功要求新 receipt 和模型实体校验。
未知脚本不推断成功契约：需 manifest 明确输入和预期实体，未声明则 BLOCKED。
静态路径检测属于兼容性检查，不是任意 Python 的安全沙箱。

## 模块与交付顺序

1. scanner.py：项目识别、别名/重名冲突；dependencies.py：内嵌接口识别及 manifest。
2. executor.py / cae_worker.py：隔离副本、Abaqus 调用、运行证据与模型校验。
3. state.py / runner.py：连续阶段计划、串行执行、指纹和 CAE 检查点、JSON/CSV、边界停止。
4. cli.py：scan/full/resume/from；gui.py：Tkinter；scripts/build_batch_runner_exe.ps1。
5. 模拟执行器覆盖全部调度场景；真实 Abaqus 冒烟另行记录，不将模拟结果称为真实建模。

安全停止：允许当前阶段完成保存，之后不启动下一阶段；不强杀数据库保存进程。
未知/动态输入、手改保存逻辑、Python 2 中文路径以及许可证都是集成验证重点。
