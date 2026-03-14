import os
import torch
import numpy as np
import pyxdf
import joblib
import json
from scipy.signal import lfilter, butter, iirnotch
import torch.nn as nn

# ---------------- 1. 模型结构定义 (必须与 onlinev50pro.py 完全一致) ----------------

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=1500):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))
    def forward(self, x): return x + self.pe[:, :x.size(1), :]

class SmallTransformer(nn.Module):
    def __init__(self, d_model=128, nhead=4, num_layers=2, dim_feedforward=256, dropout=0.1):
        super().__init__()
        enc = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward, dropout, batch_first=True, activation='gelu')
        self.trm = nn.TransformerEncoder(enc, num_layers)
        self.pe = PositionalEncoding(d_model)
    def forward(self, x): return self.trm(self.pe(x))

class TabNetHeadPlaceholder(nn.Module):
    def __init__(self, input_dim, n_classes):
        super().__init__()
        self.layers = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, 256), nn.GELU(), nn.Dropout(0.3),
            nn.Linear(256, 128), nn.GELU(), nn.Dropout(0.5),
            nn.Linear(128, n_classes)
        )
    def forward(self, x): return self.layers(x)

class EEGNetLight(nn.Module):
    def __init__(self, n_channels, n_times, n_classes=4, csp_dim=6):
        super().__init__()
        self.temporal = nn.Sequential(
            nn.Conv1d(n_channels, 64, kernel_size=7, padding=3, bias=False),
            nn.BatchNorm1d(64), nn.GELU()
        )
        self.proj = nn.Linear(64, 128)
        self.trm = SmallTransformer(d_model=128)
        self.csp_fc = nn.Sequential(nn.Linear(csp_dim, 64), nn.GELU(), nn.Dropout(0.4))
        self.head = TabNetHeadPlaceholder(128 + 64, n_classes)
    def forward(self, x, csp_feat):
        t = self.temporal(x).permute(0, 2, 1)
        t = self.trm(self.proj(t)).mean(dim=1)
        csp_out = self.csp_fc(csp_feat)
        return self.head(torch.cat([t, csp_out], dim=1))

# ---------------- 2. 核心推理引擎 (量级与逻辑对齐) ----------------

class BCIInferenceEngine:
    def __init__(self, artifacts_dir):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"正在加载模型产物: {artifacts_dir}")
        
        with open(os.path.join(artifacts_dir, "model_config.json"), 'r') as f:
            self.config = json.load(f)
        self.csp = joblib.load(os.path.join(artifacts_dir, "best_csp.pkl"))
        self.scalers = joblib.load(os.path.join(artifacts_dir, "best_scalers.pkl"))
        
        # 强制对齐 25 通道与 1001 个采样点
        self.model = EEGNetLight(n_channels=25, n_times=1001, csp_dim=self.config['csp_dim']).to(self.device)
        self.model.load_state_dict(torch.load(os.path.join(artifacts_dir, "best_model.pth"), map_location=self.device))
        self.model.eval()
        
        fs = 250.0; nyq = fs / 2
        self.b_bp, self.a_bp = butter(4, [0.5/nyq, 100.0/nyq], btype='bandpass')
        self.b_notch, self.a_notch = iirnotch(50.0, 30.0, fs)
        self.label_map = {0: 'left', 1: 'right', 2: 'foot', 3: 'tongue'}

    def preprocess(self, raw_trial):
        # 1. 黄金系数对齐 (根据诊断结果设定)
        # 3.40e-11 会导致信号太小，我们直接使用诊断建议的 1.13e-06
        GOLDEN_SCALE = 1e-06 
        
        # 2. 去均值并缩放
        centered = raw_trial - np.mean(raw_trial, axis=1, keepdims=True)
        volts_data = centered * GOLDEN_SCALE 

        # 3. 因果滤波 (Causal Filtering)
        filtered = np.zeros_like(volts_data)
        for ch in range(volts_data.shape[0]):
            t1 = lfilter(self.b_bp, self.a_bp, volts_data[ch, :])
            filtered[ch, :] = lfilter(self.b_notch, self.a_notch, t1)
        
        # 4. CSP 特征提取 (必须在 Scaler 之前，对齐训练逻辑)
        csp_feat = self.csp.transform(filtered[np.newaxis, ...])
        
        # 5. 时间域标准化 (StandardScaler)
        scaled = np.zeros_like(filtered)
        for ch in range(filtered.shape[0]):
            scaled[ch, :] = self.scalers[ch].transform(filtered[ch, :].reshape(1, -1)).flatten()
        
        x_tensor = torch.from_numpy(scaled).float().unsqueeze(0).to(self.device)
        csp_tensor = torch.from_numpy(csp_feat).float().to(self.device)
        return x_tensor, csp_tensor, csp_feat[0]

    def predict(self, raw_trial):
        with torch.no_grad():
            x_tensor, csp_tensor, csp_raw = self.preprocess(raw_trial)
            logits = self.model(x_tensor, csp_tensor)
            probs = torch.softmax(logits, dim=1)
            pred_idx = torch.argmax(probs, dim=1).item()
            return self.label_map[pred_idx], probs[0, pred_idx].item(), csp_raw

# ---------------- 3. XDF 流处理与全自动通道匹配 ----------------

def get_25ch_indices(eeg_stream):
    """从 66 个通道中精准提取 BCI IV 2a 要求的 22+3 个通道索引"""
    eeg_targets = ['FZ', 'FC3', 'FC1', 'FCZ', 'FC2', 'FC4', 'C5', 'C3', 'C1', 'CZ',
                   'C2', 'C4', 'C6', 'CP3', 'CP1', 'CPZ', 'CP2', 'CP4', 'P1', 'PZ', 'P2', 'POZ']
    try:
        ch_info = eeg_stream['info']['desc'][0]['channels'][0]['channel']
        xdf_labels = [str(c['label'][0]).upper() for c in ch_info]
    except:
        print("警告：无法读取通道标签，默认使用前 25 个通道。")
        return list(range(25))

    indices = []
    # 1. 匹配 22 个 EEG 标准通道
    for t in eeg_targets:
        try:
            # 搜索包含目标标签的通道 (例如 'EEG-C3' 匹配 'C3')
            idx = next(i for i, lbl in enumerate(xdf_labels) if t == lbl or t in lbl)
            indices.append(idx)
        except StopIteration:
            pass
    
    # 2. 如果没找齐 22 个，补齐至 22 个
    if len(indices) < 22:
        print(f"匹配完成，仅找到 {len(indices)}/22 个标准通道。正在补充剩余通道...")
        for i in range(len(xdf_labels)):
            if i not in indices and len(indices) < 22:
                indices.append(i)

    # 3. 补齐最后 3 个占位通道 (凑够 25 个送入 CSP 和 Scaler)
    for i in range(len(xdf_labels)):
        if i not in indices and len(indices) < 25:
            indices.append(i)
            
    print(f"最终提取的通道索引顺序: {indices}")
    return indices

def run_xdf_inference(xdf_path, engine):
    print(f"\n正在读取测试文件: {xdf_path}")
    streams, _ = pyxdf.load_xdf(xdf_path)
    eeg_stream = next(s for s in streams if s['info']['type'][0] == 'EEG')
    
    indices = get_25ch_indices(eeg_stream)
    raw_data = eeg_stream['time_series']
    fs_xdf = float(eeg_stream['info']['nominal_srate'][0])
    
    print(f"\n{'时间(s)':<8} | {'预测结果':<10} | {'置信度':<8} | {'CSP特征均值'}")
    print("-" * 60)

    # 步长：125 点 (0.5秒)
    for start in range(15000, raw_data.shape[0] - 2002, 125):
        # 500Hz 提取 2002 个点以对齐 250Hz 下的 1001 个点
        chunk = raw_data[start : start + 2002, indices].T
        trial_250hz = chunk[:, ::2][:, :1001]
        
        if np.max(np.abs(trial_250hz)) < 1e-7: continue
            
        label, conf, csp_vals = engine.predict(trial_250hz)
        print(f"{start/fs_xdf:<8.1f} | {label:<10s} | {conf:<8.3f} | {np.mean(csp_vals):.2f}")

if __name__ == "__main__":
    # 路径配置
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    ARTIFACTS_DIR = os.path.join(project_root, "code", "online", "onlinev50pro")
    XDF_PATH = os.path.join(project_root, "Data", "xdf", "eeg_workflow_20260312_181155.xdf")

    if os.path.exists(ARTIFACTS_DIR):
        engine = BCIInferenceEngine(ARTIFACTS_DIR)
        if os.path.exists(XDF_PATH):
            run_xdf_inference(XDF_PATH, engine)
        else:
            print(f"未找到 XDF 文件: {XDF_PATH}")
    else:
        print(f"未找到模型产物目录: {ARTIFACTS_DIR}")
