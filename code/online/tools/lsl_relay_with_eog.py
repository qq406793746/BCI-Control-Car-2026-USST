#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import numpy as np
import mne
from pylsl import StreamInlet, resolve_byprop, StreamInfo, StreamOutlet

# ================= 配置区域 =================
OFFLINE_EOG_PATH = r"D:\data\BCICIV_2a_gdf\A03E.gdf" # 替换为实际路径
FS_SRC = 500.0
FS_DST = 250.0

class Decimator:
    def __init__(self): 
        self.odd_flag = False
    def process(self, chunk):
        start_idx = 1 if self.odd_flag else 0
        self.odd_flag = (chunk.shape[1] % 2 != 0) ^ self.odd_flag
        return chunk[:, start_idx::2]

def get_target_22_indices(info):
    target_22 = [
        'FZ', 'FC3', 'FC1', 'FCZ', 'FC2', 'FC4', 'C5', 'C3', 'C1', 'CZ',
        'C2', 'C4', 'C6', 'CP3', 'CP1', 'CPZ', 'CP2', 'CP4', 'P1', 'PZ', 'P2', 'POZ'
    ]
    ch_xml = info.desc().child("channels").child("channel")
    xdf_labels = []
    while ch_xml.name():
        lbl = ch_xml.child_value("label")
        if not lbl: lbl = ch_xml.child_value("name")
        xdf_labels.append(str(lbl).upper().replace("EEG-", ""))
        ch_xml = ch_xml.next_sibling()
        
    indices = []
    for t in target_22:
        try:
            indices.append(xdf_labels.index(t))
        except ValueError:
            pass
            
    if len(indices) < 22:
        print("[警告] 缺失标准通道，强行取前 22 个。")
        return list(range(22))
    return indices

def load_continuous_eog(path):
    print(f"[Relay] 正在加载连续 EOG: {path}")
    raw = mne.io.read_raw_gdf(path, preload=True, verbose=False)
    eog_picks = [i for i, ch in enumerate(raw.ch_names) if 'EOG' in ch.upper()]
    if not eog_picks: eog_picks = [-3, -2, -1]
        
    # MNE 读出为 Volts，转换为 uV 与硬件推流单位统一
    eog_data_uv = raw.get_data(picks=eog_picks) / 1e-06 
    print(f"[Relay] 连续 EOG 加载成功！总样本数: {eog_data_uv.shape[1]}")
    return eog_data_uv

def run_relay():
    continuous_eog = load_continuous_eog(OFFLINE_EOG_PATH)
    total_eog_samples = continuous_eog.shape[1]
    global_eog_ptr = 0  # 全局时间指针
    
    print("[Relay] 正在寻找底层 LSL 流...")
    streams = resolve_byprop("type", "EEG", timeout=10.0)
    if not streams:
        print("[错误] 未找到底层 LSL，请先启动 xdf_sender！")
        return
        
    inlet = StreamInlet(streams[0])
    idx_22 = get_target_22_indices(inlet.info())
    print("[Relay] 已连接底层硬件流。")
    
    info_out = StreamInfo("BCI_Relay_25ch", "EEG", 25, FS_DST, "float32", "relay_001")
    outlet = StreamOutlet(info_out)
    print("[Relay] ⚙️ 中转站开始广播，严密时间轴拼接中...")
    
    decimator = Decimator()
    
    try:
        while True:
            chunk, ts = inlet.pull_chunk(timeout=1.0)
            if not chunk: continue
            
            arr_22 = np.array(chunk, dtype=np.float32).T[idx_22, :]
            arr_250hz = decimator.process(arr_22)
            n_samples = arr_250hz.shape[1]
            if n_samples == 0: continue
            
            # 从离线 EOG 中切出严格等长的片段
            end_ptr = global_eog_ptr + n_samples
            if end_ptr <= total_eog_samples:
                eog_chunk = continuous_eog[:, global_eog_ptr:end_ptr]
            else:
                available = total_eog_samples - global_eog_ptr
                eog_chunk = np.zeros((3, n_samples), dtype=np.float32)
                if available > 0:
                    eog_chunk[:, :available] = continuous_eog[:, global_eog_ptr:total_eog_samples]
                
            global_eog_ptr = end_ptr 
            
            arr_25 = np.vstack([arr_250hz, eog_chunk])
            outlet.push_chunk(arr_25.T.tolist())
            
    except KeyboardInterrupt:
        print("\n[Relay] 中转站关闭。")

if __name__ == "__main__":
    run_relay()