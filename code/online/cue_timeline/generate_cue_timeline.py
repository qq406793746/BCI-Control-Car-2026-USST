import os

import mne
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "Data", "BCICIV_2a_gdf")
SUBJECT_ID = 5


def generate():
    gdf_path = os.path.join(DATA_DIR, f"A0{SUBJECT_ID}E.gdf")
    print(f"Reading {gdf_path}...")

    raw = mne.io.read_raw_gdf(gdf_path, preload=False, verbose=False)
    events, event_id = mne.events_from_annotations(raw, verbose=False)

    target_id = None
    for key, value in event_id.items():
        if "783" in key:
            target_id = value
            break

    if target_id is None:
        print("Error: No 783 event found in GDF.")
        return

    cues = events[events[:, 2] == target_id][:, 0]
    output_file = os.path.join(os.path.dirname(__file__), f"cue_timeline{SUBJECT_ID}.txt")
    np.savetxt(output_file, cues, fmt="%d")

    print(f"Successfully saved {len(cues)} cue points to {output_file}")
    print(f"First 5 points: {cues[:5]}")


if __name__ == "__main__":
    generate()
