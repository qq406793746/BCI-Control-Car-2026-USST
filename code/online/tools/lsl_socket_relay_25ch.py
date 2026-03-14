#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LSL 中转脚本（按你现在的链路改）：
- 上游：LSL，500 Hz，通道里没有 EOG
- 中转：严格挑出 BCI Competition IV 2a 的 22 个 EEG 通道
- 再额外补 3 个“占位无关通道”（默认 Fp1, Fpz, Fp2）
- 形成 25 通道后做 500 -> 250 抽取
- 下游：按 receiver.py 当前 socket 协议发送
        先发 4 字节通道数，再发 b'D' + 4字节长度 + float32 数据

重要约定：
1. 发给 receiver 的 25 通道顺序固定为：
   [22 个目标 EEG] + [3 个占位通道]
2. 所以后续 receiver 要删掉“最后 3 个通道”，而不是按 EOG 名字删。
3. 这 3 个占位通道只是凑到 25 通道用，不参与模型。
4. 脚本会一直等 LSL 流出现，所以你可以先开它，再开发送端。
"""

import socket
import struct
import time
import traceback
from typing import Dict, List

import numpy as np
from pylsl import StreamInlet, resolve_byprop


# ================= 配置 =================
# LSL 输入
LSL_PROP = "name"
LSL_VALUE = "SAGA"              # 改成你的真实流名
LSL_RESOLVE_TIMEOUT = 3.0
LSL_CHUNK_TIMEOUT = 1.0
LSL_MAX_SAMPLES = 128

# socket 输出
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 65432

# 采样率
SRC_FS = 500
DST_FS = 250
DOWNSAMPLE_FACTOR = SRC_FS // DST_FS

# 输出统计
PRINT_EVERY_SEC = 2.0

# ================= 目标通道 =================
# BCI Competition IV 2a 的 22 个 EEG
TARGET_22_EEG_NAMES: List[str] = [
    "Fz",
    "FC3", "FC1", "FCz", "FC2", "FC4",
    "C5", "C3", "C1", "Cz", "C2", "C4", "C6",
    "CP3", "CP1", "CPz", "CP2", "CP4",
    "P1", "Pz", "P2",
    "POz",
]

# 额外补的 3 个占位无关通道
# 这些通道只为凑到 25 通道，后续在 receiver 里删除
DUMMY_3_NAMES: List[str] = [
    "Fp1",
    "Fpz",
    "Fp2",
]

# 最终发出的 25 通道顺序
FORWARD_25_NAMES: List[str] = TARGET_22_EEG_NAMES + DUMMY_3_NAMES

# 通道别名，可按你设备情况补充
CHANNEL_ALIASES: Dict[str, str] = {
    # 常见 EEG 前缀
    "EEG-Fz": "Fz",
    "EEG-FC3": "FC3",
    "EEG-FC1": "FC1",
    "EEG-FCz": "FCz",
    "EEG-FC2": "FC2",
    "EEG-FC4": "FC4",
    "EEG-C5": "C5",
    "EEG-C3": "C3",
    "EEG-C1": "C1",
    "EEG-Cz": "Cz",
    "EEG-C2": "C2",
    "EEG-C4": "C4",
    "EEG-C6": "C6",
    "EEG-CP3": "CP3",
    "EEG-CP1": "CP1",
    "EEG-CPz": "CPz",
    "EEG-CP2": "CP2",
    "EEG-CP4": "CP4",
    "EEG-P1": "P1",
    "EEG-Pz": "Pz",
    "EEG-P2": "P2",
    "EEG-POz": "POz",
    "EEG-Fp1": "Fp1",
    "EEG-Fpz": "Fpz",
    "EEG-Fp2": "Fp2",
}


class DownsampleByFactor:
    """固定因子抽取，跨 chunk 保持相位连续。"""
    def __init__(self, factor: int):
        if factor < 1:
            raise ValueError("factor must be >= 1")
        self.factor = factor
        self.global_sample_index = 0

    def process(self, chunk_ch_by_t: np.ndarray) -> np.ndarray:
        if self.factor == 1:
            self.global_sample_index += chunk_ch_by_t.shape[1]
            return chunk_ch_by_t

        n_samples = chunk_ch_by_t.shape[1]
        idx = np.arange(n_samples, dtype=np.int64) + self.global_sample_index
        keep = (idx % self.factor) == 0
        self.global_sample_index += n_samples
        return chunk_ch_by_t[:, keep]


def normalize_name(name: str) -> str:
    s = (name or "").strip()
    if s in CHANNEL_ALIASES:
        s = CHANNEL_ALIASES[s]
    if s.startswith("EEG-"):
        s = s[4:]
    return s


def extract_lsl_channel_names(info) -> List[str]:
    """从 LSL 元数据里读通道 label/name。"""
    names: List[str] = []
    try:
        channels = info.desc().child("channels")
        ch = channels.child("channel")
        while ch and ch.name():
            label = ch.child_value("label") or ch.child_value("name")
            names.append(label if label else f"ch{len(names)}")
            ch = ch.next_sibling()
    except Exception:
        return []
    return names


def build_channel_index_map(src_names: List[str], target_names: List[str]) -> List[int]:
    norm_src = [normalize_name(x) for x in src_names]
    src_lookup = {name: idx for idx, name in enumerate(norm_src)}

    idxs: List[int] = []
    missing: List[str] = []

    for tgt in target_names:
        key = normalize_name(tgt)
        if key not in src_lookup:
            missing.append(tgt)
        else:
            idxs.append(src_lookup[key])

    if missing:
        raise RuntimeError(
            "LSL 流里缺少目标通道: " + ", ".join(missing) + "\n"
            f"当前读到的源通道名: {src_names}"
        )
    return idxs


def resolve_lsl_inlet() -> StreamInlet:
    print(f"[LSL] 正在查找流: {LSL_PROP}={LSL_VALUE!r} ...")
    while True:
        streams = resolve_byprop(LSL_PROP, LSL_VALUE, timeout=LSL_RESOLVE_TIMEOUT)
        if streams:
            inlet = StreamInlet(streams[0], max_chunklen=LSL_MAX_SAMPLES)
            info = inlet.info()
            print(
                f"[LSL] 已连接: name={info.name()}, type={info.type()}, "
                f"channels={info.channel_count()}, srate={info.nominal_srate()}"
            )
            return inlet

        print("[LSL] 还没找到发送端，继续等待...")
        time.sleep(1.0)


def make_server() -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(1)
    return server


def send_handshake(conn: socket.socket, n_channels: int):
    conn.sendall(struct.pack("!I", n_channels))


def send_data_chunk(conn: socket.socket, data_ch_by_t: np.ndarray):
    if data_ch_by_t.size == 0:
        return
    if data_ch_by_t.dtype != np.float32:
        data_ch_by_t = data_ch_by_t.astype(np.float32, copy=False)
    payload = np.ascontiguousarray(data_ch_by_t).tobytes(order="C")
    conn.sendall(b"D" + struct.pack("!I", len(payload)) + payload)


def relay_once(conn: socket.socket, inlet: StreamInlet, pick_indices: List[int], src_names: List[str]):
    ds = DownsampleByFactor(DOWNSAMPLE_FACTOR)

    send_handshake(conn, len(pick_indices))
    print(f"[SOCKET] 已发送握手，下游通道数 = {len(pick_indices)}")

    print("[MAP] 本次发送的 25 通道映射如下：")
    for i, src_idx in enumerate(pick_indices):
        tag = "EEG " if i < 22 else "DUM "
        print(f"  [{i:02d}] {tag}{FORWARD_25_NAMES[i]:>4s} <- src[{src_idx:02d}] {src_names[src_idx]}")

    t_start = time.time()
    t_last = t_start
    in_total = 0
    out_total = 0

    declared_channels = inlet.info().channel_count()

    while True:
        chunk, _ = inlet.pull_chunk(timeout=LSL_CHUNK_TIMEOUT, max_samples=LSL_MAX_SAMPLES)
        if not chunk:
            continue

        arr = np.asarray(chunk, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        # arr: (n_samples, n_src_channels)
        if arr.shape[1] != declared_channels:
            print(f"[WARN] 本块通道数异常: declared={declared_channels}, actual={arr.shape[1]}")
            continue

        # 选 25 通道并按目标顺序重排
        picked = arr[:, pick_indices]      # (n_samples, 25)
        picked = picked.T                  # (25, n_samples)

        in_total += picked.shape[1]

        out_chunk = ds.process(picked)     # (25, n_samples_down)
        out_total += out_chunk.shape[1]

        send_data_chunk(conn, out_chunk)

        now = time.time()
        if now - t_last >= PRINT_EVERY_SEC:
            total_elapsed = max(now - t_start, 1e-6)
            recent_elapsed = max(now - t_last, 1e-6)
            print(
                f"[STAT] 累计输入={in_total} 点, 累计输出={out_total} 点, "
                f"平均输入≈{in_total/total_elapsed:.1f}Hz, 平均输出≈{out_total/total_elapsed:.1f}Hz, "
                f"最近窗口≈{out_chunk.shape[1]/recent_elapsed:.1f}Hz"
            )
            t_last = now


def main():
    server = make_server()
    print(f"[SOCKET] 已开始监听: {LISTEN_HOST}:{LISTEN_PORT}")
    print("[SOCKET] 你可以先开本脚本，再开发送端和 receiver。")

    inlet = resolve_lsl_inlet()
    info = inlet.info()

    src_names = extract_lsl_channel_names(info)
    if not src_names:
        raise RuntimeError(
            "没有从 LSL 元数据里读到通道名，无法按名字严格对齐。"
        )

    print(f"[LSL] 源通道名({len(src_names)}): {src_names}")

    pick_indices = build_channel_index_map(src_names, FORWARD_25_NAMES)

    while True:
        print("[SOCKET] 等待 receiver 连接...")
        conn, addr = server.accept()
        print(f"[SOCKET] 已连接: {addr}")

        try:
            relay_once(conn, inlet, pick_indices, src_names)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            print("[SOCKET] 下游断开，返回等待重连。")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[ERROR] relay_once 异常: {e}")
            traceback.print_exc()
        finally:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断退出。")
    except Exception as e:
        print(f"[FATAL] {e}")
        traceback.print_exc()
