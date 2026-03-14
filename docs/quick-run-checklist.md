# One-Page Run Checklist

## 适用场景

这份清单只解决一件事：
- 以后你自己快速把项目跑起来

不要求你先看懂代码。

## 先确认的事

项目根目录：
- `G:\小车\BCI-Control-Car`

当前这份 `.xdf` 数据文件应在：
- `Data/xdf/eeg_workflow_20260312_181155.xdf`

推荐 Python：
- `3.9`

## 如果 VS Code 还报库没导入

如果编辑器里提示：

```text
Import "pylsl" could not be resolved
```

先选解释器：

1. `Ctrl+Shift+P`
2. `Python: Select Interpreter`
3. 选择：
   `C:\Users\123\AppData\Local\Programs\Python\Python39\python.exe`
4. 再执行：
   `Developer: Reload Window`

## 最常用的 3 种运行方式

### 1. 最简单：直接验证 `.xdf` 能不能推理

用途：
- 最省时间
- 不需要开多个终端

命令：

```bash
py code/online/analysis/xdf_inference_test.py
```

看到持续输出分类结果，就说明这条链路是通的。

### 2. 更接近在线流程：`.xdf` 仿真推理

用途：
- 比上面更接近真实在线处理
- 但仍然不需要 `LSL`

命令：

```bash
py code/online/tools/run_xdf_simulation.py
```

看到持续输出类别、置信度和 `CSP` 结果，就说明这条链路是通的。

### 3. 在线链路：`.xdf -> LSL -> 推理`

用途：
- 验证在线流处理链路
- 需要两个终端同时运行

终端 1：

```bash
py code/online/analysis/lsl_auto_cue_inference.py
```

终端 2：

```bash
py code/online/tools/xdf_lsl_sender.py
```

看到发送端开始推流、推理端开始继续运行并输出结果，就说明这条链路是通的。

## 运行顺序建议

如果你时间很少，就按这个顺序：

1. 先跑：

```bash
py code/online/analysis/xdf_inference_test.py
```

2. 需要更像在线，再跑：

```bash
py code/online/tools/run_xdf_simulation.py
```

3. 只有在你要测实时流时，再跑：

```bash
py code/online/analysis/lsl_auto_cue_inference.py
py code/online/tools/xdf_lsl_sender.py
```

## 运行前注意事项

### 1. 跑 `LSL` 前先关旧窗口

如果你之前开过旧的 `sender` 或 `inference`，先把旧终端关掉再重新开。

原因：
- 系统里如果残留旧的 `SAGA_Simulator` 流，推理端可能接到旧流

### 2. 当前 `LSL` 链路的流名

当前发送端和推理端已经统一为：

```text
SAGA_Simulator
```

不要再手动改成 `BCI_Relay_25ch`，否则会重新连不上。

### 3. 当前发送端输出格式

当前 `xdf_lsl_sender.py` 已经做了对齐：
- 输出 `25` 通道
- 输出 `250Hz`

这是为了匹配当前模型输入。

### 4. 有警告但不影响当前运行

当前已知可能会看到：
- `scikit-learn` 版本警告
- `torch.load` 的 `FutureWarning`

现状：
- 目前不影响项目跑通

## 你后面最该看的文档

如果以后忘了怎么接着跑，优先看这几份：

1. `docs/quick-run-checklist.md`
2. `docs/session-log-2026-03-14-xdf-lsl-rerun.md`
3. `docs/environment-setup.md`
4. `docs/rerun-guide.md`

## 一句话版

你以后最常用的其实就三组命令：

```bash
py code/online/analysis/xdf_inference_test.py
```

```bash
py code/online/tools/run_xdf_simulation.py
```

```bash
py code/online/analysis/lsl_auto_cue_inference.py
py code/online/tools/xdf_lsl_sender.py
```
