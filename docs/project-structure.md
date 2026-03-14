# 项目结构说明

这份文档说明这次目录整理的思路，以及“原位置”和“新位置”的对应关系。

## 整理目标

- 保留 `code/` 和 `Data/` 两个你最熟悉的主入口
- 不改核心主脚本文件名
- 把分析、工具、草稿、媒体、文档从主流程中分离出来
- 尽量让 VS Code 侧边栏一眼能分出“主线”和“附属材料”

## 顶层结构

```text
.
├── code/      # 源码
├── Data/      # 数据与数据附加材料
├── docs/      # 补充文档和报告
└── README.md  # 项目总览入口
```

## `code/` 结构

### `code/offline/`

保留原有版本式组织，不做大改：

- `v42/`
- `v65/`

这样做的原因：

- 你原来的版本脉络比较清楚
- 脚本和模型产物是按版本绑定的
- 再往下拆会增加理解成本

### `code/online/`

这里原来最杂，所以只做了轻量分层。

#### 核心运行入口

这些文件保留在 `code/online/` 根下：

- `sender.py`
- `receiver.py`
- `receiver_i_trigger.py`
- `onlinev50pro.py`
- `onlinev50pro/`
- `cue_timeline/`

原因：

- 它们构成在线链路的主入口
- 其中有些脚本使用相对路径访问 `onlinev50pro/` 或 `cue_timeline/`
- 保持原位比全面改路径更稳妥

#### `analysis/`

把分析与验证性质的内容统一收进来：

- `lsl_auto_cue_inference.py`
- `onlinev50pro_online_analysis.py`
- `xdf_inference_test.py`
- `accuracy_analysis/`

#### `tools/`

把辅助工具脚本统一放这里：

- `lsl_relay_with_eog.py`
- `xdf_lsl_sender.py`
- `lsl_socket_relay_25ch.py`
- `check_artifacts.py`
- `validate_data_loading.py`
- `run_xdf_simulation.py`

#### `scratch/`

把临时脚本单独放出来，避免和正式入口混在一起：

- `manual_lsl_trigger_receiver.py`

#### `media/`

把演示素材和备份从主代码层移开：

- `BCI_Stimulus_Review(3).mp4`
- `last_processed_frame.png`
- `onlinev50pro.zip`

#### `archive/`

用于放本地保留的重复副本或历史备份，这些内容不属于公开仓库主线：

- `onlinev50pro_duplicate_copy/`

## `Data/` 结构

```text
Data/
├── BCICIV_2a_gdf/  # 原始 GDF 数据
├── A0xE/           # MAT 数据
└── notes/          # 截图、补充 txt、说明性材料
```

这里没有动数据集本身，只把零散的图片和说明文本移到 `notes/`。

## 文档结构

### `README.md`

作为项目总入口，负责：

- 简述项目是什么
- 告诉你先看哪里
- 说明新的目录分层逻辑

### `docs/`

用于放补充文档：

- `project-structure.md`
- `usage-guide.md`
- `github-publish.md`
- `reports/`

## 这次没有做的事

- 没有统一重命名所有历史脚本
- 没有重构离线/在线代码为 Python package
- 没有删除模型产物和原始数据
- 没有大面积修改脚本内部绝对路径

这样做是为了保留你对原项目结构的熟悉感，并降低整理后的运行风险。
