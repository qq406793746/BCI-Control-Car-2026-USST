# 重跑项目最小步骤

这份文档只针对当前最容易先跑起来的主链路：

- `code/online/cue_timeline/generate_cue_timeline.py`
- `code/online/receiver.py`
- `code/online/sender.py`

## 1. 环境

当前 Python 环境已经安装好了项目依赖。

如果要在别的机器上复现：

```bash
py -m pip install -r requirements.txt
```

## 2. 数据目录

当前默认数据路径已经改为仓库相对路径：

```text
Data/BCICIV_2a_gdf/
```

也就是说，`sender.py` 和 `generate_cue_timeline.py` 会默认读取项目根目录下的：

```text
Data/BCICIV_2a_gdf
```

## 3. 先生成 cue timeline

在项目根目录运行：

```bash
py code/online/cue_timeline/generate_cue_timeline.py
```

当前默认：

- `SUBJECT_ID = 5`
- 输入文件：`Data/BCICIV_2a_gdf/A05E.gdf`
- 输出文件：`code/online/cue_timeline/cue_timeline5.txt`

## 4. 启动接收端

```bash
py code/online/receiver.py
```

当前默认：

- `HOST = 127.0.0.1`
- `PORT = 65432`
- 模型目录：`code/online/onlinev50pro/`
- timeline 文件：`code/online/cue_timeline/cue_timeline0tt.txt`

如果你要和刚生成的 `cue_timeline5.txt` 严格对齐，需要把 `receiver.py` 里的 `TIMELINE_FILE` 改成对应文件。

## 5. 启动发送端

另开一个终端运行：

```bash
py code/online/sender.py
```

当前默认：

- `SUBJECT_ID = 8`
- 数据目录：`Data/BCICIV_2a_gdf/`

## 6. 你现在最需要先注意的地方

`sender.py` 和 `generate_cue_timeline.py` 默认被试编号不一致：

- `generate_cue_timeline.py` 默认 `SUBJECT_ID = 5`
- `sender.py` 默认 `SUBJECT_ID = 8`

如果你要重跑一条一致的链路，建议先把这两个脚本改成同一个编号。

## 7. 还保留历史绝对路径的脚本

当前这些脚本还保留旧机器上的绝对路径，不影响最小在线主链路，但会影响更完整的分析/训练流程：

- `code/offline/v42/v42.py`
- `code/offline/v65/v65.py`
- `code/offline/v65/v65_offline_analysis.py`
- `code/online/analysis/`
- `code/online/tools/` 的部分脚本

如果你下一步要完整重训或跑 XDF/LSL 实验，建议继续逐个改成相对路径或统一配置文件。
