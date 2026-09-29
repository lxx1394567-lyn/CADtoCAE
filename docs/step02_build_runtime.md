# Step02 Windows GUI 构建与启动检查

保持现有 PyInstaller onedir/windowed 架构。使用可正常导入 tkinter 的 Python 3.10+，并安装项目既有构建依赖；构建命令通过参数指定解释器，不修改系统 PATH。

```powershell
.\scripts\build_step02_exe.ps1 -Python <已验证构建环境的python.exe>
.\scripts\smoke_step02_exe.ps1
```

`step02_tk_runtime.py` 在选定的解释器中导入 tkinter、ctypes，解析 `_tkinter.pyd` / `_ctypes.pyd` 的依赖名，并查询 Windows 实际加载的 Tcl、Tk、FFI DLL 路径。构建脚本将它们通过 `--add-binary` 纳入 `_internal`。不猜测安装位置，不将 DLL 放入 Git。

构建前检查 tkinter 及 Tcl 初始化是否成功；构建后检查 `_tkinter.pyd`、检测到的 DLL、`_tcl_data/init.tcl`、`_tk_data/tk.tcl`。数据目录继续由 PyInstaller 的 Tk hook 收集，不重复复制。`build/step02/tk-runtime.json` 记录实际解释器、版本和 DLL 来源。

启动检查会启动当前输出 EXE，要求检测到 `CADtoCAE Step02 Part...` 主窗口标题并继续存活至少 3 秒，随后只关闭本次启动的进程。启动错误窗口、提前退出或超时均判失败。这个检查不替代人工文件选择、脚本生成和 Abaqus 验证。

## 本次故障

失败包包含 `_tkinter.pyd` 和 Tcl/Tk 数据目录，却未包含 `tcl86t.dll` / `tk86t.dll`。同时 `_ctypes.pyd` 依赖的 `ffi.dll` 也未打包。这解释了“构建成功但启动时 DLL load failed”：开发 Python 能借助原安装目录加载 DLL，分发包不能依赖该路径。

历史 Step02 Analysis-00.toc 指向旧 Step02 worktree 的 `.venv_step02_build`，该虚拟环境基于 Anaconda Python 3.11.7，PyInstaller 6.22.2。旧可用包中的 Tcl DLL 与当前源安装中的 DLL 哈希一致。历史 spec 没有显式收集条目，不能仅凭旧 spec 断言 DLL 曾由何种额外步骤加入。

直接使用完整 Anaconda 环境也必须通过 PyInstaller 环境检查。本机完整环境虽可导入 tkinter，但存在 PyInstaller 不兼容的旧 pathlib 回移包；不要为此次构建擅自卸载用户环境的包，应复用已验证的隔离构建环境。

重新打包前应关闭旧 Step02 EXE；Windows 会锁定仍在运行的程序，导致 PyInstaller 无法覆盖输出目录。本次修复属于正式构建流程修复，不是手工向 dist 复制 DLL 的临时措施。
