# Step07 当前 MDB 原位运行验证记录

日期：2026-10-20。项目：DP_ANG14_FA03521S-T0104-02。

## 架构审查结论

原 p7_run 根据前序报告/文件哈希选择 CAE，执行 copy → open → apply → saveAs → close → reopen。ALREADY_COMPLETE 来自已有报告及输出文件。此入口不适合人工连续操作当前模型。

新增独立 u7_run，直接使用 abaqus.mdb。默认 GUI 改用 generate_inplace。旧生成器和自动验证函数保留在开发源码中，用户 EXE 不开放旧执行命令。AST 依赖裁剪使正常 PY 不包含 p7_run、sg_dispatch 或各历史保存/打开入口；生成器另行拒绝数据库切换、保存、复制、启动进程调用。

## 已完成验证

真实 Abaqus/CAE 2020 内核（独立 noGUI 开发进程，在测试目录副本上运行）；不是声称已代替用户完成桌面 File → Run Script 人工验收。

| 阶段 | 结果 | 当前模型验证 |
|---|---|---|
| 01 Tie | SUCCESS | 新增12、保留原6，总18；17实例连通；清理原生残留网格；重复执行重新核验后 ALREADY_COMPLETE |
| 02 分析步 | SUCCESS | Initial → STEP07_PRELOAD → STEP07_LOADING；两个步骤均按原参数；重复执行重新核验 |
| 03 BC | SUCCESS | 2基础固定+8檩条壳端约束；Tie路线不加实体檩托端U2；区域/自由度/传播重新核验 |
| 04 Mesh | REVIEW_REQUIRED | 46,846节点，24,348单元；58个问题单元保留待审；未降低质量阈值 |
| 05 Load | 阻断，无修改 | 用户尚未提供荷载；无假定荷载 |
| 06 INP | 阻断，无修改 | 等待05完成，不创建Job或提交计算 |

全部用户脚本调用保持 MDB 路径不变，未新增 CAE。开发驱动在脚本之外显式保存 developer_final_review.cae，仅位于测试目录。原始 hole_setup.cae SHA256 前后相同：9df06af6ab8385980b797eee29b5bba6728d067fe1cab6738711a476963d5dbe。

跳过01直接运行02/03的负向测试被阻断，模型对象清单未变。独立EXE实际启动成功，标题为0.7.0当前MDB原位执行。通过EXE生成六个脚本，生产工作目录原有46个CAE的清单、大小及修改时间保持一致。72项自动化测试通过；旧模拟测试有2条ResourceWarning，不影响通过结果。

证据：step07_runs/inplace070_exe/validation.json、exe_ui.json、delivery_no_cae_changes.json、template_consistency.json 及 Step07_Logs。最终状态排序的小修正另做真实运行验证，见 final_status_validation.json。

## 本轮修改文件

- src/cadtocae/step07_inplace.py：新原位生成器及禁用调用审计。
- src/cadtocae/step07_inplace_runtime.py：新当前MDB入口、前序对象复核、重复执行判断、失败恢复提示。
- src/cadtocae/step07_runtime_bundle.py：支持独立入口依赖裁剪，原开发入口默认兼容。
- src/cadtocae/step07_pipeline_desktop.py：移除CAE/前序报告选择，稳定脚本名及覆盖确认。
- scripts/step07_analysis_setup_gui.py：原位生成CLI，用户EXE阻断旧自动运行命令。
- scripts/build_step07_exe.ps1：打包新Runtime及使用说明。
- tests/test_step07_inplace.py：输出、入口隔离、覆盖及身份检查。
- docs/step07_inplace_usage.md、docs/step07_inplace_validation.md：说明与验证记录。

未修改 Tie 几何、网格算法、前序源码、BatchRunner。未提交、推送或新建Worktree。

## 限制

辅助分区和网格清理不能可靠整体回滚；失败后需人工恢复上次保存的CAE。网格警告尚未人工接受，不得继续05。05/06独立文件当前只提供明确阻断，不能视为功能已完成。实际桌面菜单执行及人工检查仍待用户验收。
