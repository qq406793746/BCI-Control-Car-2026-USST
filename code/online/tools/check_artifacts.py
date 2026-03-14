#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import torch
import joblib

# 替换为你的实际 artifacts 文件夹路径
ARTIFACTS_DIR = r"C:\Users\Pythsen\Desktop\BCI-Control-Car\code\online\onlinev50pro"

def check_artifacts():
    print(f"正在检查文件夹: {ARTIFACTS_DIR}\n" + "="*40)

    # 1. 检查模型权重 (best_model.pth)
    model_path = os.path.join(ARTIFACTS_DIR, "best_model.pth")
    if os.path.exists(model_path):
        state_dict = torch.load(model_path, map_location="cpu")
        # 寻找第一层卷积层的权重
        # EEGNetLight 的第一层是 self.temporal[0] (Conv1d)
        conv1_weight = state_dict.get('temporal.0.weight')
        if conv1_weight is not None:
            # Conv1d weight shape: (out_channels, in_channels, kernel_size)
            in_channels = conv1_weight.shape[1]
            print(f"✅ [PyTorch 模型] 期望输入通道数: {in_channels}")
        else:
            print("❌ 未在模型中找到 'temporal.0.weight'，请确认模型结构。")
    else:
        print("❌ 找不到 best_model.pth")

    # 2. 检查标准化器 (best_scalers.pkl)
    scalers_path = os.path.join(ARTIFACTS_DIR, "best_scalers.pkl")
    if os.path.exists(scalers_path):
        scalers = joblib.load(scalers_path)
        # scalers 是一个列表，里面存放了每个通道的 StandardScaler
        print(f"✅ [Scalers 列表] 包含的通道数: {len(scalers)}")
    else:
        print("❌ 找不到 best_scalers.pkl")

    # 3. 检查 CSP (best_csp.pkl)
    csp_path = os.path.join(ARTIFACTS_DIR, "best_csp.pkl")
    if os.path.exists(csp_path):
        csp = joblib.load(csp_path)
        # MNE 的 CSP 对象在 fit 之后，filters_ 属性的形状是 (n_channels, n_channels)
        if hasattr(csp, 'filters_'):
            csp_channels = csp.filters_.shape[1]
            print(f"✅ [CSP 空间滤波] 期望输入通道数: {csp_channels}")
        else:
            print("❌ CSP 对象缺少 'filters_' 属性，可能未被正确 fit。")
    else:
        print("❌ 找不到 best_csp.pkl")

    print("="*40)

if __name__ == "__main__":
    check_artifacts()