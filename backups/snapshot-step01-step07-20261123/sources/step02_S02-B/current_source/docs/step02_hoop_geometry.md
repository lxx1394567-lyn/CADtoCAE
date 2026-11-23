# Step02 HOOP 等厚反向弯折截面

参数格式仍为 `HOOP(D=...,W=...,T=...,L=...,R=...,RF=...)`，输入单位仍为 mm，建模单位为 m。

## 表面与半径

- X：左右直板；主圆弧凸向 +Y；Z：宽度 W 的拉伸方向。
- 功能内轮廓：主圆弧半径 `Ri=D/2`，直板配合线 `Y=0`。
- 功能外轮廓：主圆弧半径 `Ro=Ri+T`，直板外侧线 `Y=T`。
- RF 表示过渡处**弯曲内侧的小半径**。由于这里是反向弯折，小半径位于功能外轮廓；功能内轮廓的过渡半径为 `RF+T`。
- 两个过渡圆弧同心，半径差严格为 T。主圆弧同心，半径差也为 T；直板两侧距离为 T。

因此 `RF=T=3 mm` 对应 R3/R6，不能将“弯曲内侧”与“功能内表面”当作同一个概念。

## 显式几何

令 `r=Ri`，`f=RF+T`，`a=sqrt(r*(r+2*f))`。左右过渡圆心为 `(-a,f)`、`(a,f)`。

对任一侧圆心 C：

- 主内圆切点为 `C*r/(r+f)`；直板内侧切点为 `(±a,0)`。
- 主外圆切点为 `C*(r+T)/(r+f)`；直板外侧切点为 `(±a,T)`。

使用显式 Line/ArcByCenterEnds 构造两条轮廓、封闭左右端部并拉伸。不调用 Sketch.offset 或 FilletByRadius。正 RF 时所有连接相切，主圆弧两端被过渡圆角截短。

| RF | 处理 |
|---|---|
| RF=0 | 功能外轮廓的零半径过渡退化为尖角，不生成零半径圆弧；功能内轮廓仍有半径 T 的过渡。属于有意允许的极限情况，不满足“两侧均为正半径圆角”。 |
| 0<RF<T | 两侧分别为 RF、RF+T，均正常构造。 |
| RF=T | 两侧分别为 T、2T，没有退化。 |
| RF>T | 两侧分别为 RF、RF+T，正常构造。 |

## L/R 兼容规则

保留历史几何基准，不改变已有端部位置：

```
左端 X = -(Ri+T)-L
右端 X = +(Ri+T)+R
```

L/R 是从未倒圆的主外圆理论端点起算的输入延伸长度，**不是 RF 切点到板端的净平直长度**。

新的净平直长度分别为 `Ri+T+L-a`、`Ri+T+R-a`。左/右、长/短关系保持不变。RF 过大导致任一净平直长度不为正时明确报错，不缩小 RF 或悄悄移动板端。非有限尺寸、非正 D/W/T/L/R 和负 RF 同样报错。

## 实现与验证

两份入口 `scripts/abaqus_build_parts.py`、`scripts/make_cae_runner.py` 使用相同的 `_hoop_band_dimensions()`、`_hoop_band_profile_geometry()` 几何计算和显式绘制。后者嵌入生成脚本，不增加 Abaqus 运行时文件依赖。

`tests/test_hoop_profile.py` 覆盖两入口一致性、半径/厚度/相切/端部尺寸、无自交、错误输入，以及现有 Step04 的 SP 成对旋转和 DP 非对称翻转。Step04 源码未改。

`scripts/validate_hoop_in_abaqus.py` 在 Abaqus 2020 中验证实际实体、圆边半径、解析截面积与体积、两入口一致性，并调用生成的 Step04 `_instance()`，检查实际配合面和参考圆柱面的重合位置与相反法向。它只实例化 HOOP 对和参考立柱，不执行整架装配或求解。

示例命令（从当前 worktree 的 `outputs/hoop_validation` 运行）：

```powershell
abaqus cae noGUI="../../scripts/validate_hoop_in_abaqus.py" -- --cases cases.json --report abaqus_validation_report.json --cae hoop_validation.cae --legacy-script "../../scripts/abaqus_build_parts.py"
```

cases.json 是本地验证输入列表，每项包含 `name`、新生成 Step02 脚本的绝对路径 `runner`、当前 Step04 脚本的绝对路径 `assembly`、HOOP `component`、成对 instance plan 列表 `pairs` 和对应 `groups`。这些项目生成文件不纳入 Git。

本次真实输入为 ANG14（D60/W40/T3/L57/R117/RF3）及 ANG35（D60/W50/T5/L80/R50/RF5），均从现有项目工作簿重新生成 Step02 脚本。验证结果见本地 `outputs/hoop_validation/abaqus_validation_report.json`；CAE 内含每个测试的 HOOP 配对及参考立柱，可供人工复核。
