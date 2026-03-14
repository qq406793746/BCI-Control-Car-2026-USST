# 环境依赖说明

这个项目是一个 Python 项目，核心依赖集中在 EEG 数据处理、机器学习/深度学习、以及在线流处理三类。

## MNE 是什么

`MNE` 是一个 Python 库，主要用于脑电 EEG、脑磁 MEG 等神经信号的数据读取、预处理、事件提取和分析。

在这个项目里，`MNE` 主要负责：

- 读取 `.gdf` EEG 数据文件
- 从标注中提取事件
- 截取 epoch 时间窗
- 做 CSP 特征提取前的基础数据处理

简单理解：

- `NumPy` 负责数组运算
- `SciPy` 负责信号处理
- `MNE` 负责脑电数据这一层的专业操作

## requirements.txt 里的库分别做什么

### 核心数值与绘图

- `numpy`
  数组和矩阵运算，是所有 EEG 数据处理的基础
- `scipy`
  信号处理库，项目里用它做带通滤波、陷波滤波、降采样等
- `matplotlib`
  可视化波形和结果
- `joblib`
  保存和加载 `CSP`、`Scaler` 等对象
- `scikit-learn`
  提供 `StandardScaler`、`StratifiedKFold`、指标函数等

### EEG / BCI

- `mne`
  专门处理 EEG/MEG 数据，是这个项目读取 `.gdf` 和提取事件的核心库

### 深度学习

- `torch`
  也就是 PyTorch，用来定义模型、训练模型和在线推理

### 流处理 / 数据格式

- `pylsl`
  用于连接和发送 LSL 实时数据流
- `pyxdf`
  用于读取 `.xdf` 文件

## 当前环境建议

- Python：`3.9`
- 安装方式：

```bash
py -m pip install -r requirements.txt
```

## 额外提醒

- 这个项目当前还保留了一些硬编码绝对路径
- 如果你准备重新跑训练或在线推理，除了安装依赖，还需要把数据集路径改到你本机实际位置
