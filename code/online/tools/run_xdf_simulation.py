import os
import torch
import numpy as np
import pyxdf
import joblib
import json
import torch.nn as nn
import torch.nn.functional as F
from scipy.signal import butter, iirnotch, lfilter, lfilter_zi, decimate

# ================= 1. 模型定义 (严格对齐训练脚本) =================

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=1500):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))
    def forward(self, x):
        seq_len = x.size(1)
        return x + self.pe[:, :seq_len, :]

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
        self.trm = SmallTransformer(d_model=128, nhead=4, num_layers=2)
        self.csp_fc = nn.Sequential(nn.Linear(csp_dim, 64), nn.GELU(), nn.Dropout(0.4))
        self.head = TabNetHeadPlaceholder(128 + 64, n_classes)
    def forward(self, x, csp_feat):
        t = self.temporal(x).permute(0, 2, 1)
        t = self.trm(self.proj(t)).mean(dim=1)
        csp_out = self.csp_fc(csp_feat)
        return self.head(torch.cat([t, csp_out], dim=1))

# ================= 2. 状态滤波器 (复用 Receiver 逻辑) =================

class OnlineFilter:
    def __init__(self, n_channels, fs=250.0):
        nyq = fs / 2
        self.b_bp, self.a_bp = butter(4, [0.5/nyq, 100.0/nyq], btype='bandpass')
        self.b_notch, self.a_notch = iirnotch(50.0, 30.0, fs)
        self.n_channels = n_channels
        self.zi_bp_unit = lfilter_zi(self.b_bp, self.a_bp)
        self.zi_notch_unit = lfilter_zi(self.b_notch, self.a_notch)
        self.initialized = False
        self.zi_bp = None
        self.zi_notch = None

    def init_state(self, first_sample):
        self.zi_bp = np.zeros((self.n_channels, len(self.zi_bp_unit)))
        self.zi_notch = np.zeros((self.n_channels, len(self.zi_notch_unit)))
        for i in range(self.n_channels):
            self.zi_bp[i] = self.zi_bp_unit * first_sample[i]
        self.initialized = True

    def process(self, chunk):
        if not self.initialized: 
            self.init_state(chunk[:, 0])
        filtered = np.zeros_like(chunk)
        for i in range(self.n_channels):
            out_bp, self.zi_bp[i] = lfilter(self.b_bp, self.a_bp, chunk[i], zi=self.zi_bp[i])
            out_notch, self.zi_notch[i] = lfilter(self.b_notch, self.a_notch, out_bp, zi=self.zi_notch[i])
            filtered[i] = out_notch
        return filtered

# ================= 3. 推理核心控制 =================

class XDFRigorousProcessor:
    def __init__(self, artifacts_dir):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[System] 正在加载模型配置与权重...")
        
        # 加载配置
        with open(os.path.join(artifacts_dir, "model_config.json"), 'r') as f:
            self.config = json.load(f)
        self.model_channels = self.config['n_channels'] # 获取模型实际需要的通道数
        self.n_times = self.config.get('n_times', 1001)
        
        # 加载预处理器
        self.csp = joblib.load(os.path.join(artifacts_dir, "best_csp.pkl"))
        self.scalers = joblib.load(os.path.join(artifacts_dir, "best_scalers.pkl"))
        
        # 加载模型
        self.model = EEGNetLight(
            n_channels=self.model_channels, 
            n_times=self.n_times, 
            n_classes=4, 
            csp_dim=self.config['csp_dim']
        ).to(self.device)
        self.model.load_state_dict(torch.load(os.path.join(artifacts_dir, "best_model.pth"), map_location=self.device))
        self.model.eval()
        
        # 初始化状态
        self.filter = OnlineFilter(self.model_channels, fs=250.0)
        self.buffer = np.zeros((self.model_channels, self.n_times), dtype=np.float32)
        self.label_map = {0: 'Left', 1: 'Right', 2: 'Foot', 3: 'Tongue'}

    def map_bci2a_channels(self, xdf_labels):
        """严格匹配 BCI 2a 的 22 个通道顺序"""
        target_22 = [
            'FZ', 'FC3', 'FC1', 'FCZ', 'FC2', 'FC4', 'C5', 'C3', 'C1', 'CZ',
            'C2', 'C4', 'C6', 'CP3', 'CP1', 'CPZ', 'CP2', 'CP4', 'P1', 'PZ', 'P2', 'POZ'
        ]
        labels_upper = [str(l).upper() for l in xdf_labels]
        
        indices = []
        missing = []
        for t in target_22:
            if t in labels_upper:
                indices.append(labels_upper.index(t))
            else:
                missing.append(t)
        
        if missing:
            print(f"[警告] 你的 XDF 缺失以下标准通道: {missing}。将强制使用前 {len(target_22)} 个通道作为平替。")
            indices = list(range(22))
        else:
            print(f"[成功] 完美匹配 22 个 BCI 2a 标准通道。")
            
        return indices

    def process_and_predict(self, raw_chunk_250hz):
        """接收降采样到 250Hz 的数据块，滤波并送入缓存"""
        
        # 1. 单位转换 (uV -> V) 严格遵循物理法则
        chunk_volts = raw_chunk_250hz * 1e-6
        
        # 2. 因果滤波
        filtered_chunk = self.filter.process(chunk_volts)
        n_new = filtered_chunk.shape[1]
        
        # 3. 更新滑动窗口缓存
        self.buffer = np.roll(self.buffer, -n_new, axis=1)
        self.buffer[:, -n_new:] = filtered_chunk
        
        # 4. 执行推理 (逻辑与 receiver.py 完全一致)
        trial_data = self.buffer[np.newaxis, :, :]
        temp_input = self.buffer.copy()
        
        # StandardScaler 处理
        for ch in range(self.model_channels):
            s_idx = ch if ch < len(self.scalers) else -1
            temp_input[ch] = self.scalers[s_idx].transform(temp_input[ch].reshape(1, -1)).flatten()
        
        t_in = torch.from_numpy(temp_input[np.newaxis, :, :]).float().to(self.device)
        c_feat = self.csp.transform(trial_data)
        c_in = torch.from_numpy(c_feat).float().to(self.device)
        
        with torch.no_grad():
            logits = self.model(t_in, c_in)
            probs = F.softmax(logits, dim=1)
            
        conf, p_idx = torch.max(probs, dim=1)
        return self.label_map[p_idx.item()], conf.item(), np.mean(c_feat)

# ================= 4. 主执行流程 =================

def run_xdf_simulation(xdf_path, artifacts_dir):
    print("\n" + "="*50)
    print(f"XDF 严谨离线推流启动")
    print("="*50)

    # 1. 初始化引擎
    processor = XDFRigorousProcessor(artifacts_dir)
    
    # 2. 读取 XDF
    streams, _ = pyxdf.load_xdf(xdf_path)
    eeg_stream = next(s for s in streams if s['info']['type'][0] == 'EEG')
    
    fs_xdf = float(eeg_stream['info']['nominal_srate'][0])
    raw_data = eeg_stream['time_series']
    xdf_labels = [c['label'][0] for c in eeg_stream['info']['desc'][0]['channels'][0]['channel']]
    
    # 3. 获取通道索引
    indices_22 = processor.map_bci2a_channels(xdf_labels)
    
    print(f"[推流] 原始采样率: {fs_xdf}Hz (将自动降采样至 250Hz)")
    print(f"[推流] 数据总长度: {raw_data.shape[0] / fs_xdf:.1f} 秒")
    print("-" * 50)
    print(f"{'时间 (s)':<8} | {'预测动作':<8} | {'置信度':<8} | {'CSP均值'}")
    
    # 4. 模拟实时推流 (每 0.2 秒推进一次)
    step_500hz = int(fs_xdf * 0.2) # 500Hz 下的 100 个点
    start_idx = int(fs_xdf * 10)   # 跳过前 10 秒不稳定期
    
    for ptr in range(start_idx, raw_data.shape[0] - step_500hz, step_500hz):
        # 提取 500Hz 原始切片
        chunk_500hz = raw_data[ptr : ptr + step_500hz, indices_22].T
        
        # 降采样到 250Hz [cite: 48]
        if abs(fs_xdf - 500.0) < 1.0:
            chunk_250hz = decimate(chunk_500hz, 2, axis=1) # 科学抗混叠降采样
        else:
            chunk_250hz = chunk_500hz
            
        # --- 维度适配：如果模型要 25 个通道，自动补齐 3 个全零通道 ---
        if processor.model_channels > 22:
            pad_ch = processor.model_channels - 22
            zeros = np.zeros((pad_ch, chunk_250hz.shape[1]), dtype=np.float32)
            chunk_250hz = np.vstack([chunk_250hz, zeros])
        elif processor.model_channels < 22:
            chunk_250hz = chunk_250hz[:processor.model_channels, :]
            
        # 推理
        label, conf, csp_m = processor.process_and_predict(chunk_250hz)
        
        # 打印结果
        current_time = ptr / fs_xdf
        print(f"{current_time:<8.1f} | {label:<8s} | {conf:<8.3f} | {csp_m:.2f}")

if __name__ == "__main__":
    # ==== 请检查并修改这里的路径 ====
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    ARTIFACTS_DIR = os.path.join(project_root, "code", "online", "onlinev50pro")
    XDF_PATH = os.path.join(project_root, "Data", "xdf", "eeg_workflow_20260312_181155.xdf")
    
    run_xdf_simulation(XDF_PATH, ARTIFACTS_DIR)
