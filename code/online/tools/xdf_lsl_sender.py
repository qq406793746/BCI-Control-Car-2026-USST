#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time

import pyxdf
from pylsl import StreamInfo, StreamOutlet

# ================= 配置区域 =================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
XDF_FILE_PATH = os.path.join(PROJECT_ROOT, "Data", "xdf", "eeg_workflow_20260312_181155.xdf")

def run_xdf_sender():
    print(f"[Sender] 正在加载 XDF 文件: {XDF_FILE_PATH} ...")
    
    try:
        streams, file_header = pyxdf.load_xdf(XDF_FILE_PATH)
    except Exception as e:
        print(f"[错误] 读取 XDF 失败: {e}")
        return

    # 寻找 EEG 数据流
    eeg_stream = None
    for stream in streams:
        if stream['info']['type'][0] == 'EEG':
            eeg_stream = stream
            break
            
    if eeg_stream is None:
        print("[错误] 未找到 'EEG' 数据流。")
        return

    data = eeg_stream['time_series']
    srate = float(eeg_stream['info']['nominal_srate'][0])
    n_channels = int(eeg_stream['info']['channel_count'][0])
    total_samples = len(data)
    
    print(f"[Sender] 找到 EEG 流！通道数: {n_channels}, 采样率: {srate}Hz, 样本数: {total_samples}")

    # 创建 LSL 广播站
    info = StreamInfo(name="SAGA_Simulator", type="EEG", channel_count=n_channels, 
                      nominal_srate=srate, channel_format="float32", source_id="sim_xdf_001")
     
    channels_xml = info.desc().append_child("channels")
    try:
        for ch in eeg_stream['info']['desc'][0]['channels'][0]['channel']:
            channels_xml.append_child("channel").append_child_value("label", ch['label'][0])
    except:
        for i in range(n_channels):
            channels_xml.append_child("channel").append_child_value("label", f"Ch{i}")

    outlet = StreamOutlet(info)
    
    # 【核心：握手等待机制】
    print("[Sender] LSL 广播站已启动！")
    print("[Sender] ⏳ 正在等待中转站(Relay Node)接入...")
    while not outlet.have_consumers():
        time.sleep(0.1) 
        
    print("[Sender] ⚡ 检测到接入！发令枪响，开始从第 0 秒严格同步推流...")

    chunk_size = 10 
    sleep_time = chunk_size / srate

    try:
        for i in range(0, total_samples, chunk_size):
            end_idx = i + chunk_size
            chunk = data[i:end_idx]
            outlet.push_chunk(chunk.tolist())
            time.sleep(sleep_time)
            
        print("\n[Sender] 数据发送完毕。")
    except KeyboardInterrupt:
        print("\n[Sender] 手动停止发送。")

if __name__ == "__main__":
    run_xdf_sender()
