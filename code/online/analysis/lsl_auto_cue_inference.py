#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LSL 推理端 (全自动 Cue 触发版)
------------------------------------------------
1. 直接连接 Relay 节点的 25通道 250Hz LSL 流
2. 读取 cue_timeline3.txt 中的精确样本索引
3. 在连续数据流中侦测当前样本数，到达 Cue 点自动回溯截取最完美的 1001 点
4. 彻底消除按键延迟，实现 100% 离线复刻对齐
"""

import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import joblib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.signal import butter, iirnotch, lfilter, lfilter_zi
from pylsl import StreamInlet, resolve_byprop

# ================= 配置区域 =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

# 确保这个目录里有 best_model.pth, best_csp.pkl, best_scalers.pkl
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "code", "online", "onlinev50pro")
CUE_FILE_PATH = os.path.join(PROJECT_ROOT, "code", "online", "cue_timeline", "cue_timeline5.txt")

GOLDEN_SCALE = 1e-06     
FS_DST = 250.0           
WINDOW_SIZE = 1001       

PLOT_WINDOW = 750   
TOTAL_DURATION_MIN = 47
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
LABEL_MAP = {0: 'Left', 1: 'Right', 2: 'Foot', 3: 'Tongue'}

PLOT_CHANNELS = [7, 9, 11] # C3, Cz, C4
PLOT_LABELS = ['C3 (uV)', 'Cz (uV)', 'C4 (uV)']
PLOT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c']
MODEL_CHANNELS = 25
VIS_CHANNELS = 22

# ================= 模型定义 =================
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
        self.trm = SmallTransformer(d_model=128, nhead=4, num_layers=2)
        self.csp_fc = nn.Sequential(nn.Linear(csp_dim, 64), nn.GELU(), nn.Dropout(0.4))
        self.head = TabNetHeadPlaceholder(128 + 64, n_classes)
    def forward(self, x, csp_feat):
        t = self.temporal(x).permute(0, 2, 1)
        t = self.trm(self.proj(t)).mean(dim=1)
        csp_out = self.csp_fc(csp_feat)
        return self.head(torch.cat([t, csp_out], dim=1))

# ================= 状态组件 =================
class OnlineFilter:
    def __init__(self, n_channels, fs=250.0):
        nyq = fs / 2
        self.b_bp, self.a_bp = butter(4, [0.5/nyq, 100.0/nyq], btype='bandpass')
        self.b_notch, self.a_notch = iirnotch(50.0, 30.0, fs)
        self.n_channels = n_channels
        self.zi_bp_unit = lfilter_zi(self.b_bp, self.a_bp)
        self.zi_notch_unit = lfilter_zi(self.b_notch, self.a_notch)
        self.initialized = False
        self.zi_bp = None; self.zi_notch = None

    def init_state(self, first_sample):
        self.zi_bp = np.zeros((self.n_channels, len(self.zi_bp_unit)))
        self.zi_notch = np.zeros((self.n_channels, len(self.zi_notch_unit)))
        for i in range(self.n_channels):
            self.zi_bp[i] = self.zi_bp_unit * first_sample[i]
            self.zi_notch[i] = self.zi_notch_unit * first_sample[i]
        self.initialized = True

    def process(self, chunk):
        if not self.initialized: self.init_state(chunk[:, 0])
        filtered = np.zeros_like(chunk)
        for i in range(self.n_channels):
            out_bp, self.zi_bp[i] = lfilter(self.b_bp, self.a_bp, chunk[i], zi=self.zi_bp[i])
            out_notch, self.zi_notch[i] = lfilter(self.b_notch, self.a_notch, out_bp, zi=self.zi_notch[i])
            filtered[i] = out_notch
        return filtered

# ================= 核心推演 =================
class BCIProcessor_LSL:
    def __init__(self):
        print("[System] 正在加载模型权重与 CSP...")
        self.csp = joblib.load(os.path.join(ARTIFACTS_DIR, "best_csp.pkl"))
        self.scalers = joblib.load(os.path.join(ARTIFACTS_DIR, "best_scalers.pkl"))
        
        self.model = EEGNetLight(n_channels=MODEL_CHANNELS, n_times=WINDOW_SIZE, n_classes=4, csp_dim=6).to(DEVICE)
        self.model.load_state_dict(torch.load(os.path.join(ARTIFACTS_DIR, "best_model.pth"), map_location=DEVICE))
        self.model.eval()

        # 【核心修正】：读取你的 txt 时间轴，转为整数列表
        try:
            with open(CUE_FILE_PATH, 'r') as f:
                self.cue_list = [int(line.strip()) for line in f if line.strip().isdigit()]
            print(f"[System] 成功加载时间轴，共找到 {len(self.cue_list)} 个触发点。")
        except Exception as e:
            print(f"[致命错误] 无法读取 Cue 文件 {CUE_FILE_PATH}: {e}")
            self.cue_list = []
            
        self.current_cue_idx = 0

        self.filter = OnlineFilter(n_channels=MODEL_CHANNELS, fs=FS_DST)
        
        # 【核心修正】：为了应对 LSL Chunk 的数据溢出，缓存区加大 100 个点，保证回溯不出错
        self.buffer = np.zeros((MODEL_CHANNELS, WINDOW_SIZE *3), dtype=np.float32)
        self.vis_buffer = np.zeros((VIS_CHANNELS, PLOT_WINDOW)) 
        
        self.total_samples = 0
        self.last_result = None

    def process_chunk(self, chunk_250hz):
        if chunk_250hz.shape[0] != MODEL_CHANNELS:
            print(
                f"[Warn] Expected {MODEL_CHANNELS} channels but received "
                f"{chunk_250hz.shape[0]}. Truncating/padding to match the model."
            )
            if chunk_250hz.shape[0] > MODEL_CHANNELS:
                chunk_250hz = chunk_250hz[:MODEL_CHANNELS, :]
            else:
                pad = np.zeros(
                    (MODEL_CHANNELS - chunk_250hz.shape[0], chunk_250hz.shape[1]),
                    dtype=chunk_250hz.dtype,
                )
                chunk_250hz = np.vstack([chunk_250hz, pad])

        chunk_volts = chunk_250hz * GOLDEN_SCALE
        filtered = self.filter.process(chunk_volts)
        n_new = filtered.shape[1]

        # 正常推进入缓存
        self.buffer = np.roll(self.buffer, -n_new, axis=1)
        self.buffer[:, -n_new:] = filtered
        
        self.vis_buffer = np.roll(self.vis_buffer, -n_new, axis=1)
        self.vis_buffer[:, -n_new:] = filtered[:VIS_CHANNELS, :]

        self.total_samples += n_new

       # -------------------------------------------------------------------
        # 【自动触发判定】：检查当前总样本数是否迈过了下一个 Cue
        # -------------------------------------------------------------------
        if self.current_cue_idx < len(self.cue_list):
            current_cue_start = self.cue_list[self.current_cue_idx]
            target_inference_sample = current_cue_start + WINDOW_SIZE

            # 一旦跨过目标点，立刻启动计算
            if self.total_samples >= target_inference_sample:
                offset = self.total_samples - target_inference_sample
                
                result = self.run_inference(offset)
                
                # 无论推理是否成功，都要把指针推向下一个 Cue，防止死循环卡死
                self.current_cue_idx += 1
                
                # 【核心拦截】：只有 result 真的有数据时，才返回 True 通知界面去解包
                if result is not None:
                    self.last_result = result
                    return True
                else:
                    return False
                
        return False

    def run_inference(self, offset):
        try:
            # 绝对精准的切片：扣除由于 Chunk 带来的超发偏移量
            if offset == 0:
                current_trial = self.buffer[:, -WINDOW_SIZE:]
            else:
                current_trial = self.buffer[:, -(WINDOW_SIZE + offset) : -offset]
            
            temp_input = current_trial.copy()
            for ch in range(MODEL_CHANNELS):
                temp_input[ch] = self.scalers[ch].transform(temp_input[ch].reshape(1, -1)).flatten()

            trial_data_for_csp = current_trial[np.newaxis, :, :]
            c_feat = self.csp.transform(trial_data_for_csp)
            
            t_in = torch.from_numpy(temp_input[np.newaxis, :, :]).float().to(DEVICE)
            c_in = torch.from_numpy(c_feat).float().to(DEVICE)

            with torch.no_grad():
                logits = self.model(t_in, c_in)
                probs = F.softmax(logits, dim=1)
                
            p_idx = probs.argmax().item()
            conf = probs.max().item()
            return LABEL_MAP[p_idx], conf, np.mean(c_feat)
            
        except Exception as e:
            import traceback
            print(f"\n[致命异常] 推理函数内部发生崩溃: {e}")
            traceback.print_exc()  # 把具体的报错行数和原因打印出来
            return None

# ================= UI与入口 =================
def run_visual_receiver():
    plt.ion()
    fig = plt.figure(figsize=(10, 8))
    fig.canvas.manager.set_window_title("BCI LSL Inference (Auto Cue Sync)")
    gs = gridspec.GridSpec(4, 1, height_ratios=[2, 2, 2, 1])

    axes_wave = [fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])]
    ax_prog = fig.add_subplot(gs[3])

    lines = []
    for i, ax in enumerate(axes_wave):
        line, = ax.plot(np.zeros(PLOT_WINDOW), color=PLOT_COLORS[i], lw=1.5)
        ax.set_ylabel(PLOT_LABELS[i])
        ax.set_ylim(-50, 50)
        ax.grid(True, alpha=0.3)
        lines.append(line)
    axes_wave[0].set_title("Real-time EEG Stream (Filtered)")

    total_samples_est = TOTAL_DURATION_MIN * 60 * FS_DST
    ax_prog.set_xlim(0, total_samples_est)
    ax_prog.set_ylim(0, 1)
    ax_prog.set_yticks([])
    ax_prog.set_xlabel(f"Timeline (Total {TOTAL_DURATION_MIN} mins)")

    current_time_line = ax_prog.axvline(x=0, color='red', linewidth=2)
    status_text = ax_prog.text(0.01, 1.1, "Status: Waiting for Relay...", transform=ax_prog.transAxes, fontsize=10, fontweight='bold')
    
    plt.tight_layout()

    print("[System] Looking for LSL stream named 'SAGA_Simulator' ...")
    streams = resolve_byprop("name", "SAGA_Simulator", timeout=1000.0)
    if not streams:
        print("[错误] 未找到中转流，请检查 relay_node.py 是否运行！")
        return
        
    inlet = StreamInlet(streams[0], max_chunklen=100)
    print(f"[连接成功] 已接入中转站！")
    
    processor = BCIProcessor_LSL()

    plot_counter = 0
    try:
        while True:
            chunk, timestamps = inlet.pull_chunk(timeout=1.0)
            if not chunk: 
                plt.pause(0.01)
                continue
                
            arr = np.array(chunk, dtype=np.float32).T 
            has_result = processor.process_chunk(arr)

            # 当自动判定完成一次推理时：
            if has_result:
                lbl, conf, csp_val = processor.last_result
                # 打印当前是第几个 Trial，以及具体在什么样本索引触发的
                triggered_cue_idx = processor.current_cue_idx - 1
                start_sample_point = processor.cue_list[triggered_cue_idx]
                
                print(f"  ★ [Trial {triggered_cue_idx + 1}] | 样本: {start_sample_point} | 识别: {lbl} (置信: {conf:.2f})")
                
                # 在时间轴画上标记
                ax_prog.text(processor.total_samples, 0.5, lbl[0], color='blue', fontsize=10, ha='center', fontweight='bold')

            plot_counter += arr.shape[1]
            if plot_counter >= 25: 
                vis_data = processor.vis_buffer * 1e6 
                for i, ch_idx in enumerate(PLOT_CHANNELS):
                    lines[i].set_ydata(vis_data[ch_idx, :])

                current_time_line.set_xdata([processor.total_samples])
                curr_sec = processor.total_samples / FS_DST
                curr_min = int(curr_sec // 60)
                curr_sec_rem = int(curr_sec % 60)

                if processor.current_cue_idx < len(processor.cue_list):
                    next_cue_sec = processor.cue_list[processor.current_cue_idx] / FS_DST
                    status_text.set_text(f"Time: {curr_min:02d}:{curr_sec_rem:02d} | 等待 Trial {processor.current_cue_idx + 1} (触发点: {next_cue_sec:.1f}s)")
                else:
                    status_text.set_text(f"Time: {curr_min:02d}:{curr_sec_rem:02d} | 实验已结束")

                plt.draw()
                plt.pause(0.001)
                plot_counter = 0

    except KeyboardInterrupt:
        print("\n[退出] 用户终止接收。")

if __name__ == "__main__":
    run_visual_receiver()
