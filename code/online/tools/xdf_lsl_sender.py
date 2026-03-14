#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time

import pyxdf
from pylsl import StreamInfo, StreamOutlet

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
XDF_FILE_PATH = os.path.join(PROJECT_ROOT, "Data", "xdf", "eeg_workflow_20260312_181155.xdf")


def get_25ch_indices(eeg_stream):
    """Pick the 22 BCI 2a EEG channels plus 3 fillers to match the model input."""
    eeg_targets = [
        "FZ", "FC3", "FC1", "FCZ", "FC2", "FC4", "C5", "C3", "C1", "CZ",
        "C2", "C4", "C6", "CP3", "CP1", "CPZ", "CP2", "CP4", "P1", "PZ", "P2", "POZ",
    ]

    try:
        ch_info = eeg_stream["info"]["desc"][0]["channels"][0]["channel"]
        xdf_labels = [str(channel["label"][0]) for channel in ch_info]
        labels_upper = [label.upper() for label in xdf_labels]
    except Exception:
        return list(range(25)), [f"Ch{index}" for index in range(25)]

    indices = []
    selected_labels = []

    for target in eeg_targets:
        try:
            idx = next(
                index for index, label in enumerate(labels_upper)
                if target == label or target in label
            )
            indices.append(idx)
            selected_labels.append(xdf_labels[idx])
        except StopIteration:
            continue

    if len(indices) < 22:
        for index, label in enumerate(xdf_labels):
            if index not in indices and len(indices) < 22:
                indices.append(index)
                selected_labels.append(label)

    filler_index = 0
    while len(indices) < 25:
        indices.append(indices[filler_index % len(indices)])
        selected_labels.append(f"Pad{len(indices) - 22}")
        filler_index += 1

    return indices[:25], selected_labels[:25]


def run_xdf_sender():
    print(f"[Sender] Loading XDF file: {XDF_FILE_PATH}")

    try:
        streams, _ = pyxdf.load_xdf(XDF_FILE_PATH)
    except Exception as exc:
        print(f"[Error] Failed to read XDF: {exc}")
        return

    eeg_stream = None
    for stream in streams:
        if stream["info"]["type"][0] == "EEG":
            eeg_stream = stream
            break

    if eeg_stream is None:
        print("[Error] No EEG stream found in the XDF file.")
        return

    data = eeg_stream["time_series"]
    srate = float(eeg_stream["info"]["nominal_srate"][0])
    n_channels = int(eeg_stream["info"]["channel_count"][0])
    total_samples = len(data)

    pick_indices, picked_labels = get_25ch_indices(eeg_stream)
    output_srate = 250.0 if abs(srate - 500.0) < 1.0 else srate

    print(
        f"[Sender] EEG stream found. Channels={n_channels}, "
        f"SampleRate={srate}Hz, Samples={total_samples}"
    )
    print(
        f"[Sender] Forwarding Channels={len(pick_indices)}, "
        f"OutputSampleRate={output_srate}Hz"
    )

    info = StreamInfo(
        name="SAGA_Simulator",
        type="EEG",
        channel_count=len(pick_indices),
        nominal_srate=output_srate,
        channel_format="float32",
        source_id="sim_xdf_001",
    )

    channels_xml = info.desc().append_child("channels")
    for label in picked_labels:
        channels_xml.append_child("channel").append_child_value("label", label)

    outlet = StreamOutlet(info)

    print("[Sender] LSL outlet started.")
    print("[Sender] Waiting for relay or inference consumer...")
    while not outlet.have_consumers():
        time.sleep(0.1)

    print("[Sender] Consumer detected. Starting synchronized stream...")

    chunk_size = 20 if abs(srate - 500.0) < 1.0 else 10
    sleep_time = chunk_size / srate

    try:
        for index in range(0, total_samples, chunk_size):
            end_index = index + chunk_size
            chunk = data[index:end_index, pick_indices]
            if abs(srate - 500.0) < 1.0:
                chunk = chunk[::2]
            outlet.push_chunk(chunk.tolist())
            time.sleep(sleep_time)

        print("\n[Sender] Stream finished.")
    except KeyboardInterrupt:
        print("\n[Sender] Stream stopped by user.")


if __name__ == "__main__":
    run_xdf_sender()
