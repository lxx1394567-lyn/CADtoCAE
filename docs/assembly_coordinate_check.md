# Assembly 前置坐标校核

正式 Assembly 前，先由关键尺寸输入自动计算 `A/B/C/D/E/F` 控制点坐标，并把结果写入 Excel、JSON 和标注图。当前版本不做 PNG 自动识别交点，图纸图片只用于把计算结果标注回原图，方便人工校核。

坐标体系保持：`X` 向图纸右侧，`Z` 竖直向上，`Y=0`。Abaqus 输入单位统一为 `m-kg-N-Pa`，图纸尺寸可以按 `mm` 填写。

## 新版控制点逻辑

斜梁采用局部坐标：

- `G`：斜梁 Part 左端局部起点，局部里程 `s=0`，不是必须人工定位的全局控制点。
- `F`：斜梁与上立柱/三角连接件参考交点，是全局锚点。
- `C/F/E`：斜梁上的关键截面，用局部里程 `GC/GF/GE` 表示。
- `G_global`：由 `F-GF*u` 派生出的斜梁左端全局参考点，仅用于实例放置和图纸标注。

需要填写或确认：

- `theta_deg`：斜梁与水平 `X` 轴夹角。
- `Z_A_mm`：上立柱上顶点 A 高度。
- `X_F_mm`、`Z_F_mm`：F 点全局坐标。
- `Z_BD_mm`、`R_hoop_mm`：B/D 高度与抱箍水平偏移。
- `GC_mm`、`GF_mm`、`GE_mm`：斜梁局部里程。
- `L_BC_draw_mm`、`L_DE_draw_mm`：图纸标注的前/后斜撑长度。

计算规则：

```text
u = (cos(theta), sin(theta))

A = (0, 0, Z_A)
F = (X_F, 0, Z_F)
B = (-R_hoop, 0, Z_BD)
D = (+R_hoop, 0, Z_BD)
C = F + (GC - GF) * u
E = F + (GE - GF) * u
G_global = F - GF * u
```

校核规则：

```text
GC < GF < GE
angle(CE, +X) = theta_deg, tolerance = 0.05 deg
|BC_calc - L_BC_draw| <= 0.001 m
|DE_calc - L_DE_draw| <= 0.001 m
```

## 输出命令

生成坐标控制工作簿：

```powershell
python scripts\make_coordinate_workbook.py `
  --layout examples\sp_sc_ang20_coordinate_layout.json `
  --out outputs\SP_SC_ANG20_coordinate_check.xlsx
```

生成带坐标标注的图纸：

```powershell
python scripts\annotate_coordinates.py `
  --layout examples\sp_sc_ang20_coordinate_layout.json `
  --image C:\Users\LDT\AppData\Local\Temp\codex-clipboard-f7777794-a0d7-4343-9d7b-1086c9666147.png `
  --out-png outputs\SP_SC_ANG20_annotated_coordinates.png `
  --out-pdf outputs\SP_SC_ANG20_annotated_coordinates.pdf
```

导出 Assembly 输入：

```powershell
python scripts\export_assembly_inputs.py `
  --layout examples\sp_sc_ang20_coordinate_layout.json `
  --out outputs\SP_SC_ANG20_assembly_inputs.json
```

只有关键尺寸为 `已确认`，且对应局部截面、角度或长度校核通过时，构件轴线才会进入正式 `ready_members`。未通过或未确认的数据仍保留在工作簿和草稿 JSON 中，便于复核。
