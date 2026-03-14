# 使用导览

这份文档不替代你原来的实验过程，只是把“先看什么、从哪里开始跑”整理成更清晰的导航。

## 1. 先理解目录

建议先按下面顺序看：

1. `README.md`
2. `code/offline/v42/` 和 `code/offline/v65/`
3. `code/online/`
4. `Data/`

## 2. 离线训练主线

### `v42`

入口：

- `code/offline/v42/v42.py`

特点：

- 早期版本
- 有较完整的训练指标与模型产物

### `v65`

入口：

- `code/offline/v65/v65.py`

特点：

- 相比 `v42` 做了进一步优化
- 目录里还保留了离线分析脚本和结果文件

## 3. 在线推理主线

### 数据发送端

- `code/online/sender.py`

作用：

- 从 `.gdf` 文件读取 EEG 数据
- 按时间片模拟实时发送
- 同步发送事件标记

### 接收与推理端

- `code/online/receiver.py`
- `code/online/receiver_i_trigger.py`

作用：

- 接收数据流
- 做在线滤波
- 缓存窗口
- 根据 cue timeline 在合适时刻推理
- 可视化波形与结果

### 在线模型导出

- `code/online/onlinev50pro.py`

作用：

- 训练/导出在线推理所需产物
- 输出到 `code/online/onlinev50pro/`

## 4. 你现在如何在 VS Code 里看这个项目

如果你只是想快速上手，建议只盯住这几个目录：

- `code/offline/v42`
- `code/offline/v65`
- `code/online`
- `docs`

如果你只是想清理仓库或准备上传 GitHub，重点看：

- `docs/github-publish.md`
- `code/online/media`
- `code/online/scratch`
- `Data`

## 5. 哪些内容是“主线”，哪些是“附属”

### 主线

- `code/offline/v42`
- `code/offline/v65`
- `code/online/sender.py`
- `code/online/receiver.py`
- `code/online/receiver_i_trigger.py`
- `code/online/onlinev50pro.py`
- `code/online/onlinev50pro/`
- `code/online/cue_timeline/`

### 附属但建议保留

- `code/online/analysis/`
- `docs/reports/acc data.pptx`
- `Data/notes/`

### 可后续继续人工筛选

- `code/online/tools/`
- `code/online/scratch/`
- `code/online/media/`
- `code/online/archive/`

## 6. 后续如果要继续规范化

建议顺序如下：

1. 先把核心脚本中的绝对路径改成相对路径或配置项
2. 再补 `requirements.txt`
3. 再增加 `.gitignore`
4. 最后再决定是否删除草稿脚本和大数据文件
