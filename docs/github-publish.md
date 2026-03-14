# GitHub 上传建议

这份文档面向“准备把项目传到 GitHub”的场景。

## 不建议直接上传的内容

### 原始数据

- `Data/BCICIV_2a_gdf/`
- `Data/A0xE/`

原因：

- 体积很大
- 不属于源码本身
- 更适合在文档中说明下载来源，而不是直接进仓库

### 媒体和备份

- `code/online/media/BCI_Stimulus_Review(3).mp4`
- `code/online/media/onlinev50pro.zip`
- `code/online/archive/onlinev50pro_duplicate_copy/`

### 临时/草稿脚本

- `code/online/scratch/`

## 建议优先保留上传的内容

- `README.md`
- `docs/`
- `code/offline/`
- `code/online/sender.py`
- `code/online/receiver.py`
- `code/online/receiver_i_trigger.py`
- `code/online/onlinev50pro.py`
- `code/online/onlinev50pro/`
- `code/online/cue_timeline/`

## 这次已经为公开仓库做的处理

- 统一了多个历史脚本的命名
- 把分析脚本、工具脚本、草稿脚本、媒体文件分层
- 把重复的模型副本移到了 `code/online/archive/`
- 用 `.gitignore` 排除了大数据目录和本地材料

## 如果你想做成更适合公开展示的仓库

推荐公开版结构：

```text
repo/
├── README.md
├── docs/
├── code/
└── .gitignore
```

然后在 README 里说明：

- 数据集下载地址
- 模型产物是否需要自行训练
- 哪些脚本是实验脚本，哪些是正式入口

## 当前仓库的实际情况

- 当前项目总大小仍然很大，主要来自 `Data/`
- 虽然大部分单文件未必超过 GitHub 的硬拒绝阈值，但整个仓库并不适合原样公开
- 公开前最好先把数据目录和媒体目录排除
