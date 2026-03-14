import os, torch, mne, joblib
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from scipy.signal import butter, lfilter, iirnotch
from mne.decoding import CSP
from sklearn.preprocessing import StandardScaler

# ---------------- 配置与滤波器 ----------------
DATA_DIR = r"C:\Users\Pythsen\Desktop\BCI-Control-Car\data" # 建议检查路径
FS, LOW_CUT, HIGH_CUT = 250.0, 0.5, 100.0
NYQ = 0.5 * FS
b_bp, a_bp = butter(4, [LOW_CUT/NYQ, HIGH_CUT/NYQ], btype='bandpass')
b_notch, a_notch = iirnotch(50.0, 30.0, FS)

def apply_causal_filter(data):
    for ch in range(data.shape[0]):
        data[ch, :] = lfilter(b_bp, a_bp, data[ch, :])
        data[ch, :] = lfilter(b_notch, a_notch, data[ch, :])
    return data

# ---------------- 核心加载逻辑 (修复眼电问题) ----------------
def load_pure_eeg(path):
    raw = mne.io.read_raw_gdf(path, preload=True, verbose=False)
    
    # 强制将名称中包含 'EOG' 的通道标记为 eog 类型
    mapping = {ch: 'eog' for ch in raw.ch_names if 'EOG' in ch.upper()}
    raw.set_channel_types(mapping)
    
    # 现在 pick_types 就能精准识别并剔除 EOG 了
    picks = mne.pick_types(raw.info, eeg=True, eog=False, exclude='bads')
    raw.pick(picks) 
    
    # 因果滤波与 Epoching
    data = apply_causal_filter(raw.get_data())
    raw_filt = mne.io.RawArray(data, raw.info, verbose=False)
    
    events, event_id = mne.events_from_annotations(raw_filt, verbose=False)
    # 对应 2a 数据集的四个类别：左、右、足、舌
    wanted = {'769':1, '770':2, '771':3, '772':4} 
    epochs = mne.Epochs(raw_filt, events, event_id=wanted, tmin=0.0, tmax=4.0, baseline=None, preload=True)
    
    return epochs.get_data(), epochs.events[:, -1] - 1 # 标签转为 0-3

# ---------------- 模型架构 (V50Pro 蒸馏版) ----------------
class EEGNetLight(nn.Module):
    def __init__(self, n_ch=22, n_times=1001, csp_dim=6):
        super().__init__()
        self.temporal = nn.Sequential(nn.Conv1d(n_ch, 64, 7, padding=3), nn.BatchNorm1d(64), nn.GELU())
        self.proj = nn.Linear(64, 128)
        self.trm = nn.TransformerEncoder(nn.TransformerEncoderLayer(128, 4, 256, batch_first=True), 2)
        self.csp_fc = nn.Linear(csp_dim, 64)
        self.head = nn.Sequential(nn.Linear(128 + 64, 128), nn.GELU(), nn.Linear(128, 4))

    def forward(self, x, csp_feat):
        x = self.temporal(x).permute(0, 2, 1)
        x = self.trm(self.proj(x)).mean(dim=1)
        return self.head(torch.cat([x, F.gelu(self.csp_fc(csp_feat))], dim=1))

class ShallowTeacher(nn.Module):
    def __init__(self, n_ch=22):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv2d(1, 40, (1, 25)), nn.Conv2d(40, 40, (n_ch, 1), bias=False), nn.BatchNorm2d(40))
    def forward(self, x):
        x = self.conv(x.unsqueeze(1))
        return F.log_softmax(x.flatten(1), dim=1) # 简化版 Teacher

# ---------------- 训练逻辑简述 ----------------
def train_step(student, teacher, xb, yb, cf, opt):
    student.train()
    # 蒸馏损失计算
    s_logits = student(xb, cf)
    with torch.no_grad():
        t_logits = teacher(xb)
    
    loss_ce = nn.CrossEntropyLoss()(s_logits, yb)
    loss_kd = F.kl_div(F.log_softmax(s_logits/3.0, dim=1), F.softmax(t_logits/3.0, dim=1), reduction='batchmean')
    
    loss = 0.5 * loss_ce + 0.5 * loss_kd
    opt.zero_grad(); loss.backward(); opt.step()
    return loss.item()

if __name__ == "__main__":
    # 演示：加载一个文件验证通道
    test_path = os.path.join(DATA_DIR, "A01T.gdf")
    if os.path.exists(test_path):
        X, y = load_pure_eeg(test_path)
        print(f"数据加载成功！最终特征矩阵形状: {X.shape}") 
        # 此时 X.shape[1] 应该严格等于 22
    else:
        print("未发现数据，请检查 DATA_DIR 路径")