# BCI-Control-Car

基于运动想象 EEG 的脑机接口小车项目。这个仓库覆盖了从离线训练、在线推理到小车控制/仿真的完整实验链路。

## 你现在看到的结构

本次整理遵循两个原则：

1. 保留你原来容易识别的顶层入口：`code/`、`Data/`
2. 只把原先混在一起的分析脚本、草稿脚本、媒体文件、说明文档分层归档

当前推荐从这几个入口开始看：

- `code/offline/`
  离线训练与模型评估
- `code/online/`
  在线推理、数据发送、接收和可视化
- `Data/`
  原始数据集和数据相关附加材料
- `docs/`
  补充文档、结构说明和 GitHub 上传建议

## 项目主线

### 1. 离线训练

- `code/offline/v42/v42.py`
  较早版本的离线训练脚本
- `code/offline/v65/v65.py`
  引入蒸馏思路后的离线训练版本

训练完成后会产出：

- `best_model.pth`
- `best_csp.pkl`
- `best_scalers.pkl`
- `model_config.json`

### 2. 在线仿真/推理

- `code/online/sender.py`
  从 `.gdf` 数据模拟实时 EEG 数据流
- `code/online/receiver.py`
  接收数据流、在线滤波、缓存、推理、可视化
- `code/online/receiver_i_trigger.py`
  支持手动触发推理的接收端变体
- `code/online/onlinev50pro.py`
  面向在线部署产物的训练/导出脚本

### 3. 数据集

- `Data/BCICIV_2a_gdf/`
  BCI Competition IV 2a 的 `.gdf` 数据
- `Data/A0xE/A0xE/`
  对应 `.mat` 数据

## 整理后的目录概览

```text
BCI-Control-Car/
├── README.md
├── code/
│   ├── offline/
│   │   ├── v42/
│   │   └── v65/
│   └── online/
│       ├── sender.py
│       ├── receiver.py
│       ├── receiver_i_trigger.py
│       ├── onlinev50pro.py
│       ├── onlinev50pro/
│       ├── cue_timeline/
│       ├── analysis/
│       ├── tools/
│       ├── scratch/
│       └── media/
├── Data/
│   ├── BCICIV_2a_gdf/
│   ├── A0xE/
│   └── notes/
└── docs/
    ├── project-structure.md
    ├── usage-guide.md
    ├── github-publish.md
    └── reports/
```

## 重点说明

### `code/online/analysis/`

放原本用于离线分析、效果比对、实验检查的脚本和日志，例如：

- `lsl_auto_cue_inference.py`
- `onlinev50pro_online_analysis.py`
- `xdf_inference_test.py`
- `accuracy_analysis/`

### `code/online/tools/`

放辅助工具脚本，例如：

- `lsl_relay_with_eog.py`
- `xdf_lsl_sender.py`
- `lsl_socket_relay_25ch.py`
- `check_artifacts.py`
- `validate_data_loading.py`
- `run_xdf_simulation.py`

### `code/online/scratch/`

放临时草稿或命名不规范但暂时保留的脚本：

- `manual_lsl_trigger_receiver.py`

### `code/online/media/`

放演示视频、截图、打包备份：

- `BCI_Stimulus_Review(3).mp4`
- `last_processed_frame.png`
- `onlinev50pro.zip`

### `code/online/archive/`

放本地保留但不建议进入公开仓库的备份内容，例如重复模型副本：

- `onlinev50pro_duplicate_copy/`

## 建议阅读顺序

1. 看 [`docs/project-structure.md`](./docs/project-structure.md)
2. 再看 [`docs/usage-guide.md`](./docs/usage-guide.md)
3. 如果你准备上传 GitHub，看 [`docs/github-publish.md`](./docs/github-publish.md)

## 当前已知情况

- 项目里仍然保留了一些绝对路径写法，主要存在于分析/测试脚本中
- 核心运行链路的主入口文件没有被改名，便于你继续按原思路找文件
- `Data/` 体积很大，若准备上传 GitHub，建议不要直接上传整个数据目录
- 当前 `.gitignore` 已按“公开版仓库”思路排除了数据、媒体、草稿和重复备份目录
