#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# receiver_i_trigger.py
# 在原 receiver 基础上新增：
# 1) 支持按键 i 手动触发推理
# 2) 没有 timeline 文件时，也允许进入程序并使用手动模式
# 3) 保留原有 timeline 自动触发逻辑

import socket
import struct
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import joblib
import os
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.signal import butter, iirnotch, lfilter, lfilter_zi

# ================= 配置 =================
ARTIFACTS_DIR = r"onlinev50pro"
TIMELINE_FILE = r"cue_timeline\cue_timeline5.txt"
HOST = '192.168.10.9'
PORT = 65432

WINDOW_SIZE = 1001
FS = 250.0
PLOT_WINDOW = 750   # 3秒波形窗
TOTAL_DURATION_MIN = 47
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
LABEL_MAP = {0: 'Left', 1: 'Right', 2: 'Foot', 3: 'Tongue'}
PLOT_CHANNELS = [7, 9, 11] # C3, Cz, C4
PLOT_LABELS = ['C3 (uV)', 'Cz (uV)', 'C4 (uV)']
PLOT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c']

# 新增：手动触发配置
MANUAL_TRIGGER_KEY = 'i'
MANUAL_TRIGGER_WAIT_SAMPLES = WINDOW_SIZE  # 按下 i 后，再等待约 4 秒做一次推理


# ================= 模型定义 (必须包含) =================

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
    def forward(self, x):
        x = self.pe(x)
        return self.trm(x)

class TabNetHeadPlaceholder(nn.Module):
    def __init__(self, input_dim, n_classes):
        super().__init__()
        self.layers = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, 256),
            nn.GELU(), nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.GELU(), nn.Dropout(0.5),
            nn.Linear(128, n_classes)
        )
    def forward(self, x):
        return self.layers(x)

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
        input_dim = 128 + 64 
        self.head = TabNetHeadPlaceholder(input_dim, n_classes)
    def forward(self, x, csp_feat):
        t = self.temporal(x)
        t = t.permute(0, 2, 1)
        t = self.proj(t)
        t = self.trm(t)
        tpool = t.mean(dim=1)
        csp_out = self.csp_fc(csp_feat)
        cat = torch.cat([tpool, csp_out], dim=1)
        return self.head(cat)

# ================= 处理器组件 =================

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
            self.zi_notch[i] = self.zi_notch_unit * first_sample[i]
        self.initialized = True

    def process(self, chunk):
        if not self.initialized:
            self.init_state(chunk[:, 0])
        n_ch = chunk.shape[0]
        filtered = np.zeros_like(chunk)
        for i in range(n_ch):
            out_bp, self.zi_bp[i] = lfilter(self.b_bp, self.a_bp, chunk[i], zi=self.zi_bp[i])
            out_notch, self.zi_notch[i] = lfilter(self.b_notch, self.a_notch, out_bp, zi=self.zi_notch[i])
            filtered[i] = out_notch
        return filtered

class BCIProcessor:
    def __init__(self, n_channels):
        print("[System] Loading Artifacts & Models...")
        self.csp = joblib.load(os.path.join(ARTIFACTS_DIR, "best_csp.pkl"))
        self.scalers = joblib.load(os.path.join(ARTIFACTS_DIR, "best_scalers.pkl"))
        self.model = EEGNetLight(n_channels=n_channels, n_times=WINDOW_SIZE, n_classes=4, csp_dim=6).to(DEVICE)
        self.model.load_state_dict(torch.load(os.path.join(ARTIFACTS_DIR, "best_model.pth"), map_location=DEVICE))
        self.model.eval()

        self.filter = OnlineFilter(n_channels)
        self.buffer = np.zeros((n_channels, WINDOW_SIZE), dtype=np.float32)
        self.vis_buffer = np.zeros((n_channels, PLOT_WINDOW))
        self.n_channels = n_channels
        self.total_samples = 0

        # timeline 改为可选
        self.timeline_enabled = False
        self.cue_schedule = np.array([], dtype=int)
        self.cue_pointer = 0
        self.last_triggered_cue_idx = -1

        if os.path.exists(TIMELINE_FILE):
            try:
                self.cue_schedule = np.atleast_1d(np.loadtxt(TIMELINE_FILE, dtype=int)).astype(int)
                self.timeline_enabled = True
                print(f"[System] Loaded {len(self.cue_schedule)} cues from {TIMELINE_FILE}")
            except Exception as e:
                print(f"[Warn] Timeline 加载失败，仅保留手动模式: {e}")
        else:
            print("[System] Timeline 文件不存在，仅使用手动模式。")

        self.predict_countdown = -1
        self.last_result = None
        self.pending_trigger_type = None   # 'timeline' or 'manual'

    def request_manual_inference(self):
        if self.predict_countdown > 0:
            print(f"[Manual] 当前已有待执行推理，剩余约 {max(self.predict_countdown / FS, 0):.2f}s")
            return False
        self.predict_countdown = MANUAL_TRIGGER_WAIT_SAMPLES
        self.pending_trigger_type = 'manual'
        self.last_triggered_cue_idx = -1
        print(f"\n>>> [MANUAL] 检测到按键 '{MANUAL_TRIGGER_KEY}'，约 {MANUAL_TRIGGER_WAIT_SAMPLES / FS:.2f}s 后开始推理...")
        return True

    def process_chunk(self, raw_chunk):
        filtered = self.filter.process(raw_chunk)
        n_new = filtered.shape[1]

        self.buffer = np.roll(self.buffer, -n_new, axis=1)
        self.buffer[:, -n_new:] = filtered

        self.vis_buffer = np.roll(self.vis_buffer, -n_new, axis=1)
        self.vis_buffer[:, -n_new:] = filtered

        current_pos = self.total_samples
        self.total_samples += n_new

        # Protocol Check
        if self.timeline_enabled and self.predict_countdown < 0 and self.cue_pointer < len(self.cue_schedule):
            next_cue = self.cue_schedule[self.cue_pointer]
            if current_pos <= next_cue < self.total_samples:
                print(f"\n>>> [PROTOCOL] Cue #{self.cue_pointer+1} triggered. Analyzing in {WINDOW_SIZE / FS:.2f}s...")
                self.predict_countdown = WINDOW_SIZE
                self.pending_trigger_type = 'timeline'
                self.last_triggered_cue_idx = self.cue_pointer
                self.cue_pointer += 1

        # Countdown
        if self.predict_countdown > 0:
            self.predict_countdown -= n_new
            if self.predict_countdown <= 0:
                result = self.run_inference()
                trigger_type = self.pending_trigger_type
                cue_idx = self.last_triggered_cue_idx
                self.predict_countdown = -1
                self.pending_trigger_type = None

                if result:
                    lbl, conf = result
                    self.last_result = (lbl, conf, cue_idx, trigger_type)
                    return True

        return False

    def run_inference(self):
        try:
            trial_data = self.buffer[np.newaxis, :, :]
            temp_input = self.buffer.copy()
            for ch in range(self.n_channels):
                # Scaler 越界保护
                s_idx = ch if ch < len(self.scalers) else -1
                temp_input[ch] = self.scalers[s_idx].transform(temp_input[ch].reshape(1, -1)).flatten()

            t_in = torch.from_numpy(temp_input[np.newaxis, :, :]).float().to(DEVICE)
            c_feat = self.csp.transform(trial_data)
            c_in = torch.from_numpy(c_feat).float().to(DEVICE)

            with torch.no_grad():
                logits = self.model(t_in, c_in)
                probs = F.softmax(logits, dim=1)
            p_idx = probs.argmax().item()
            conf = probs.max().item()
            return LABEL_MAP[p_idx], conf
        except Exception as e:
            print(f"Inference Error: {e}")
            import traceback
            traceback.print_exc()
            return None

# ================= 界面循环 =================

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

def run_visual_receiver():
    # --- Matplotlib 初始化 ---
    plt.ion()
    fig = plt.figure(figsize=(10, 8))
    gs = gridspec.GridSpec(4, 1, height_ratios=[2, 2, 2, 1])

    axes_wave = [fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])]
    ax_prog = fig.add_subplot(gs[3])

    # 初始化波形线
    lines = []
    for i, ax in enumerate(axes_wave):
        line, = ax.plot(np.zeros(PLOT_WINDOW), color=PLOT_COLORS[i], lw=1.5)
        ax.set_ylabel(PLOT_LABELS[i])
        ax.set_ylim(-50, 50)
        ax.grid(True, alpha=0.3)
        lines.append(line)
    axes_wave[0].set_title("Real-time EEG Stream (Filtered)")

    # 初始化进度条
    total_samples_est = TOTAL_DURATION_MIN * 60 * FS
    ax_prog.set_xlim(0, total_samples_est)
    ax_prog.set_ylim(0, 1)
    ax_prog.set_yticks([])
    ax_prog.set_xlabel(f"Timeline / Manual Trigger (Total {TOTAL_DURATION_MIN} mins)")

    # 绘制所有 Cue 点
    cue_lines = []
    cues = np.array([], dtype=int)
    if os.path.exists(TIMELINE_FILE):
        try:
            cues = np.atleast_1d(np.loadtxt(TIMELINE_FILE, dtype=int)).astype(int)
            for c in cues:
                l = ax_prog.axvline(x=int(c), color='lightgray', linewidth=2, alpha=0.8)
                cue_lines.append(l)
        except Exception as e:
            print(f"[Warn] Cue 绘制失败: {e}")

    # 红色当前进度指针
    current_time_line = ax_prog.axvline(x=0, color='red', linewidth=2)
    status_text = ax_prog.text(
        0.01, 1.1,
        f"Status: Waiting... (按 {MANUAL_TRIGGER_KEY.upper()} 手动触发)",
        transform=ax_prog.transAxes,
        fontsize=10,
        fontweight='bold'
    )

    plt.tight_layout()

    # --- Socket 连接 ---
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            print(f"[Receiver] Connecting to {HOST}:{PORT}...")
            s.connect((HOST, PORT))

            data = recv_exact(s, 4)
            if data is None:
                raise ConnectionError("未收到初始 4 字节通道数")

            n_channels = struct.unpack('!I', data)[0]
            print(f"[Receiver] Connected. Channels: {n_channels}")

            processor = BCIProcessor(n_channels)
            plot_counter = 0

            def on_key(event):
                if event.key == MANUAL_TRIGGER_KEY:
                    started = processor.request_manual_inference()
                    if started:
                        status_text.set_text(
                            f"Status: Manual trigger armed, infer in {MANUAL_TRIGGER_WAIT_SAMPLES / FS:.2f}s"
                        )
                        fig.canvas.draw_idle()

            fig.canvas.mpl_connect('key_press_event', on_key)
            print(f"[UI] 请先点击图窗获得焦点，再按 '{MANUAL_TRIGGER_KEY}' 手动触发推理。")

            while True:
                header = recv_exact(s, 1)
                if not header:
                    print("[Receiver] 连接已断开。")
                    break

                if header == b'D':
                    len_bytes = recv_exact(s, 4)
                    if len_bytes is None:
                        print("[Receiver] 数据长度头读取失败。")
                        break

                    length = struct.unpack('!I', len_bytes)[0]

                    chunks = recv_exact(s, length)
                    if chunks is None:
                        print("[Receiver] 数据体读取失败。")
                        break

                    raw_chunk = np.frombuffer(chunks, dtype=np.float32).reshape(n_channels, -1)

                    # 处理
                    has_result = processor.process_chunk(raw_chunk)

                    # 更新结果
                    if has_result:
                        lbl, conf, c_idx, trigger_type = processor.last_result
                        print(f"  ★ RESULT [{trigger_type}]: {lbl} ({conf:.2f})")

                        if trigger_type == 'timeline' and c_idx < len(cue_lines):
                            cue_lines[c_idx].set_color('green')
                            ax_prog.text(cues[c_idx], 0.5, lbl[0], color='black', fontsize=8, ha='center')
                        elif trigger_type == 'manual':
                            ax_prog.text(
                                processor.total_samples, 0.75, lbl[0],
                                color='blue', fontsize=9, ha='center', fontweight='bold'
                            )

                    # --- 绘图刷新 ---
                    plot_counter += 1
                    if plot_counter >= 10:
                        vis_data = processor.vis_buffer * 1e6 # uV
                        for i, ch_idx in enumerate(PLOT_CHANNELS):
                            if ch_idx < n_channels:
                                lines[i].set_ydata(vis_data[ch_idx, :])

                        current_time_line.set_xdata([processor.total_samples])

                        curr_sec = processor.total_samples / FS
                        curr_min = int(curr_sec // 60)
                        curr_sec_rem = int(curr_sec % 60)

                        if processor.predict_countdown > 0:
                            remain_sec = max(processor.predict_countdown / FS, 0.0)
                            mode = processor.pending_trigger_type or "pending"
                            status_text.set_text(
                                f"Time: {curr_min:02d}:{curr_sec_rem:02d} / {TOTAL_DURATION_MIN}:00 | "
                                f"{mode} infer in {remain_sec:.2f}s | 按 {MANUAL_TRIGGER_KEY.upper()} 触发"
                            )
                        else:
                            status_text.set_text(
                                f"Time: {curr_min:02d}:{curr_sec_rem:02d} / {TOTAL_DURATION_MIN}:00 | "
                                f"按 {MANUAL_TRIGGER_KEY.upper()} 手动触发"
                            )

                        plt.draw()
                        plt.pause(0.001)
                        plot_counter = 0

                elif header == b'M':
                    _ = recv_exact(s, 4)

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    run_visual_receiver()
