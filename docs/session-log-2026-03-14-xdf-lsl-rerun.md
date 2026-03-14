# Session Log 2026-03-14: XDF / LSL / Rerun Notes

## 日期

- 2026-03-14

## 本次整理目的

这份文档记录本次围绕以下主题做过的解释、修改和结论，方便下次快速接上：

- `MNE`、`CSP`、`LSL`、`XDF` 分别是什么
- 这个项目里 `.gdf` 和 `.xdf` 两条链路的区别
- 在线最小主链路如何重跑
- `.xdf` 数据文件应该放在哪里
- 哪些脚本是 `XDF / LSL / 中转端 / 推理端`

## 关键概念解释

### MNE

`MNE` 是一个 Python 库，主要用于 EEG / MEG 神经信号处理。

在本项目中，`MNE` 主要负责：

- 读取 `.gdf` 文件
- 提取事件
- 切 epoch 时间窗
- 配合 `CSP` 做特征处理

### CSP

`CSP` 是 `Common Spatial Patterns` 的缩写。

它是一种脑机接口中常见的空间特征提取方法，用来把多通道 EEG 转换成更适合分类的特征。

### LSL

`LSL` 是 `Lab Streaming Layer` 的缩写。

它是一个实验实时数据流传输与时间同步框架。

可以把它理解成：

- `LSL` 负责“传”
- 常用于 EEG、EOG、marker 等多路流的同步传输

### XDF

`XDF` 是 `Extensible Data Format` 的缩写。

可以把它理解成：

- `XDF` 负责“存”
- 常用于把 `LSL` 实时流录制下来

一句话理解关系：

```text
LSL = 直播
XDF = 直播录像
```

## `.gdf` 和 `.xdf` 的区别

### `.gdf`

偏标准脑电数据集文件，适合：

- 离线训练
- 标准离线实验
- 直接按数据集格式处理

本项目里主要用于：

- `code/offline/v42/v42.py`
- `code/offline/v65/v65.py`
- `code/online/sender.py`
- `code/online/cue_timeline/generate_cue_timeline.py`

### `.xdf`

偏实验实时流录制文件，适合：

- 在线实验回放
- LSL 多流同步数据复现
- 更接近真实在线系统链路的测试

本项目里主要用于：

- `code/online/tools/xdf_lsl_sender.py`
- `code/online/tools/run_xdf_simulation.py`
- `code/online/analysis/xdf_inference_test.py`

## 中转端是什么意思

“中转端”可以理解成数据中间站。

它一般不负责采集原始数据，也不一定负责最终分类，而是负责把上游数据整理后交给下游。

本项目里的中转端可能做这些事：

- 接收上游 `LSL` 数据流
- 做通道挑选
- 补齐缺失通道
- 做降采样
- 把 `LSL` 再转成 `socket`
- 转给推理端

可以理解成：

```text
上游数据 -> 中转端 -> 推理端
```

## `.xdf` 仿真推理是什么意思

`.xdf` 仿真推理` 的意思是：

- 不用真实设备在线采集
- 直接拿已经录好的 `.xdf` 文件
- 模拟“数据正在实时过来”
- 然后做推理

这适合调试和复现实验。

## 当前已经整理好的 `.xdf` 数据路径

当前 `.xdf` 文件已放在：

- `Data/xdf/eeg_workflow_20260312_181155.xdf`

原文件名：

- `example_EEG_workflow-20260312_181155.xdf`

当前已规范为：

- `eeg_workflow_20260312_181155.xdf`

## 已修改的相关脚本路径

以下脚本默认已改为读取仓库内相对路径下的 `.xdf`：

- `code/online/tools/xdf_lsl_sender.py`
- `code/online/tools/run_xdf_simulation.py`
- `code/online/analysis/xdf_inference_test.py`

默认目标文件：

- `Data/xdf/eeg_workflow_20260312_181155.xdf`

## `.xdf` 相关脚本怎么理解

### 1. 直接测试 `.xdf` 推理

脚本：

- `code/online/analysis/xdf_inference_test.py`

作用：

- 直接读取 `.xdf`
- 直接做推理测试

适合：

- 先验证模型能不能吃这份 `.xdf` 数据

### 2. `.xdf` 仿真推理

脚本：

- `code/online/tools/run_xdf_simulation.py`

作用：

- 读取 `.xdf`
- 做通道映射、降采样、滤波
- 更接近在线推理流程

适合：

- 想模拟在线处理过程
- 但不想真的开 `LSL` 全链路

### 3. `.xdf -> LSL` 发送端

脚本：

- `code/online/tools/xdf_lsl_sender.py`

作用：

- 把 `.xdf` 文件重新推成 `LSL` 数据流

适合：

- 用来喂给 `LSL` 推理端或中转端

### 4. `LSL` 推理端

脚本：

- `code/online/analysis/lsl_auto_cue_inference.py`

作用：

- 直接接 `LSL` 流并做推理

### 5. `LSL` 中转端

脚本：

- `code/online/tools/lsl_relay_with_eog.py`
- `code/online/tools/lsl_socket_relay_25ch.py`

作用：

- 接收上游 `LSL`
- 整理后再转发给下游

## 推荐执行顺序

建议按难度从低到高测试：

### 第一步

直接测 `.xdf` 推理：

```bash
py code/online/analysis/xdf_inference_test.py
```

### 第二步

测 `.xdf` 仿真推理：

```bash
py code/online/tools/run_xdf_simulation.py
```

### 第三步

测 `.xdf -> LSL -> 推理端`：

终端 1：

```bash
py code/online/analysis/lsl_auto_cue_inference.py
```

终端 2：

```bash
py code/online/tools/xdf_lsl_sender.py
```

### 第四步

最后再考虑加中转端。

## 当前 `.gdf` 最小在线主链路情况

当前已统一成：

- `sender.py` 默认 `SUBJECT_ID = 5`
- `generate_cue_timeline.py` 默认 `SUBJECT_ID = 5`
- `receiver.py` 默认读取 `cue_timeline5.txt`

相关文档：

- `docs/rerun-guide.md`

## 本次已经做过的环境工作

- 新增 `requirements.txt`
- 新增 `docs/environment-setup.md`
- 已完成 `pip` 安装并验证核心依赖

已验证版本：

- `mne 1.8.0`
- `torch 2.4.1+cpu`
- `numpy 1.26.4`
- `scipy 1.13.1`
- `scikit-learn 1.5.2`
- `matplotlib 3.8.4`
- `joblib 1.4.2`
- `pylsl 1.16.2`
- `pyxdf 1.16.8`

## 用户本次不明白、已解释过的点

本次明确解释过这些概念：

- `subject_id` 是被试编号
- `cue` 是实验提示时刻
- `cue timeline` 是提示时刻列表
- `MNE` 是 EEG 处理库
- `CSP` 是空间特征提取方法
- `LSL` 是实时流框架
- `XDF` 是流录制文件格式
- `中转端` 是数据中间站
- `.xdf 仿真推理` 是用录好的 `.xdf` 模拟在线推理

## 下次优先继续做什么

推荐下一步优先级：

1. 先跑：

```bash
py code/online/analysis/xdf_inference_test.py
```

2. 如果结果正常，再跑：

```bash
py code/online/tools/run_xdf_simulation.py
```

3. 如果还要验证 `LSL` 链路，再开两个终端跑：

```bash
py code/online/analysis/lsl_auto_cue_inference.py
py code/online/tools/xdf_lsl_sender.py
```

## 当前未提交的可能变更提醒

如果下次继续前要同步 GitHub，记得检查：

- `code/online/receiver.py`
- `code/online/sender.py`
- `docs/rerun-guide.md`
- `code/online/tools/xdf_lsl_sender.py`
- `code/online/tools/run_xdf_simulation.py`
- `code/online/analysis/xdf_inference_test.py`
- `Data/xdf/README.md`

## 一句话总结

下次如果忘了从哪里接：

- 先看这份文档
- 再看 `docs/rerun-guide.md`
- 再决定是走 `.gdf` 最小在线链路，还是走 `.xdf / LSL` 链路
