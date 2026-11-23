# BatchRunner V3：CAE 保存机制审查（2026-10-11）

审查在 `CADtoCAE-BatchRunner` / `feature/batch-runner` 进行，未修改原始建模算法。

项目：`SP_SC_ANG18_11042210101041S-T0202`。测试根目录：
`F:\Codex\Wind Resistance of PV Support Structures\CADtoCAE-EXE-Testing\step06test2`。

## 修改前的真实文件

以下路径均相对于测试根目录，已检查实际存在及文件大小：

| 阶段 | CAE 路径 | 字节数 |
|---|---|---:|
| 1 | `.batchrunner\20261011-085234-b228d76d\ef80becbd3bd34ac0a4b\step1\checkpoint.cae` | 204800 |
| 2 | 同批次 `step2\checkpoint.cae` | 270336 |
| 3 | 同批次 `step3\checkpoint.cae` | 393216 |
| 4 | 同批次 `step4\checkpoint.cae` | 413696 |
| 5 | `.batchrunner\20261011-085609-1e4fbd8b\ef80becbd3bd34ac0a4b\step5\checkpoint.cae` | 495616 |

## 七项结论

1. 五阶段已生成各自的 `checkpoint.cae`，位置如上，并非没有 CAE。
2. 每阶段使用独立 noGUI 进程；执行器先复制前一步检查点为 `upstream.cae`，再加载该副本。因此传递的是模型数据库内容，而非同一个持续存活的 mdb 会话。
3. `cae_worker.py` 对每一步均执行 `mdb.saveAs(pathName=...checkpoint.cae)`，包括第 5 步。保存发生在建模脚本结束、运行报告检查和 Assembly regenerate 之后。
4. 保存会包含当时 mdb 的修改；V2 保存后在同一进程重新打开，核对 Model、契约 Part、Instance、分析步名称。但 Hole/Connector 的 report 型契约没有逐项核对已保存的孔和连接。
5. V2 的 SUCCESS 除返回码外，还要求新鲜 token 收据、非空检查点、输出报告及其哈希；续跑核对脚本/输入/执行器指纹和检查点/报告哈希。
6. GUI 没有导出/交付对象、最终路径字段和模型打开按钮，因此用户只能在内部运行目录寻找检查点。
7. V2 并非完全没有可读取性检查，但缺少独立进程的最终文件语义验证，不能仅凭 V2 SUCCESS 宣称完成 V3 验收。

## V3 验证设计

独立 `delivery_worker.py` 不执行建模脚本、不 regenerate、不 save。Abaqus 2020 的 `openMdb` 本身可能更新文件内部元数据，故在新进程中打开 SHA-256 相同的验证副本。交付原件和检查点在验证前后核对哈希；保留副本、初始哈希、作业、收据和标准输出日志。

验证契约来自同一可靠链上的脚本及受哈希保护的运行报告：

- Part/Instance：契约中的准确名称，Part 非空几何。
- Analysis：报告中的 Tie、Coupling、分区特征及未抑制状态；自定义分析使用契约列出的 steps。
- Hole：报告中的每个孔特征及未抑制状态、报告计数；Step3 与最终数据库的面积/体积差、Hoop 保存体积与实例继承关系。
- Connector：命名 Wire、Section、RP、Coupling、几何区域及计数；Wire 的实际边及 SectionAssignment、Cartesian 类型、RP 位置、区域实体数量和面积/长度。精确比较 STEP06 对象名称集合，发现额外重复对象。
- 几何量采用 `max(abs(expected)*1e-4, 1e-12)` 误差容限，兼容报告质量属性近似值与 CAE getSize 精确值的差异；对象数量不采用固定阈值。

这属于建模保存与一致性验证，不是求解结果验收。当前报告的 Connector 刚度为 `TEMPORARY_PRESET`；其物理标定、承载能力、未生成的荷载及求解结果未验证。未知报告接口明确不能自动获得交付 PASSED。
