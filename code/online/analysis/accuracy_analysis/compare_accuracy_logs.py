import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_EE3 = os.path.join(BASE_DIR, "Ee5.txt")
FILE_E3 = os.path.join(BASE_DIR, "e5.txt")


def parse_ee3_table(filepath):
    data = {}
    if not os.path.exists(filepath):
        print(f"[Error] File not found: {filepath}")
        return data

    print(f"[1/3] Reading {filepath} ...")
    with open(filepath, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            match = re.search(
                r"#(\d+)\s+\|\s+(\w+)\s+\|\s+(\w+)\s+\|\s+([\d.]+)\s+\|\s+(.+)",
                line,
            )
            if not match:
                continue

            trial_id = int(match.group(1))
            true_label = match.group(2)
            pred_label = match.group(3)
            status = match.group(5).strip().lower()
            data[trial_id] = {
                "true_label": true_label,
                "pred_label": pred_label,
                "is_correct": status in {"ok", "true", "correct", "yes", "y"},
            }

    print(f"      -> Parsed {len(data)} table rows")
    return data


def parse_e3_log(filepath):
    data = {}
    if not os.path.exists(filepath):
        print(f"[Error] File not found: {filepath}")
        return data

    print(f"[2/3] Reading {filepath} ...")
    with open(filepath, "r", encoding="utf-8") as file:
        content = file.read()

    matches = re.findall(
        r"Cue #(\d+) triggered.*?RESULT: (\w+) \(([\d.]+)\)",
        content,
        re.DOTALL,
    )
    for trial_id, pred_label, conf in matches:
        data[int(trial_id)] = {
            "pred_label": pred_label,
            "conf": float(conf),
        }

    print(f"      -> Parsed {len(data)} log rows")
    return data


def main():
    ee3_data = parse_ee3_table(FILE_EE3)
    e3_data = parse_e3_log(FILE_E3)

    if not ee3_data or not e3_data:
        print("\nUnable to compare results. Check the input files first.")
        return

    print("[3/3] Comparing results...\n")
    all_ids = sorted(set(ee3_data) | set(e3_data))

    discrepancies = []
    ee3_correct = 0
    e3_correct = 0
    total_valid = 0

    print("-" * 85)
    print(
        f"{'ID':<5} | {'True':<8} | {'Ee3':<8} | {'e3':<8} | "
        f"{'Ee3 OK':<6} | {'e3 OK':<6} | Note"
    )
    print("-" * 85)

    for trial_id in all_ids:
        ee3 = ee3_data.get(trial_id)
        e3 = e3_data.get(trial_id)
        if not ee3 or not e3:
            continue

        total_valid += 1
        true_label = ee3["true_label"]
        ee3_pred = ee3["pred_label"]
        e3_pred = e3["pred_label"]

        is_ee3_right = ee3_pred == true_label
        is_e3_right = e3_pred == true_label
        is_consistent = ee3_pred == e3_pred

        if is_ee3_right:
            ee3_correct += 1
        if is_e3_right:
            e3_correct += 1

        note = ""
        if not is_consistent:
            note = "prediction mismatch"
            discrepancies.append(
                {
                    "id": trial_id,
                    "true": true_label,
                    "ee3": ee3_pred,
                    "e3": e3_pred,
                }
            )

        ee3_icon = "OK" if is_ee3_right else "ERR"
        e3_icon = "OK" if is_e3_right else "ERR"
        if not is_consistent or not is_ee3_right or not is_e3_right:
            prefix = "*" if not is_consistent else " "
            print(
                f"{prefix}{trial_id:<3} | {true_label:<8} | {ee3_pred:<8} | {e3_pred:<8} | "
                f"{ee3_icon:<6} | {e3_icon:<6} | {note}"
            )

    print("-" * 85)
    print("\n=== Summary ===")
    print(f"Total valid samples: {total_valid}")
    if total_valid:
        print(f"Ee3 accuracy: {ee3_correct}/{total_valid} ({ee3_correct / total_valid * 100:.2f}%)")
        print(f"e3 accuracy:  {e3_correct}/{total_valid} ({e3_correct / total_valid * 100:.2f}%)")

    print(f"\n=== Discrepancies ({len(discrepancies)}) ===")
    if not discrepancies:
        print("Ee3 and e3 predictions are fully consistent.")
        return

    for item in discrepancies:
        if item["e3"] == item["true"]:
            winner = "e3"
        elif item["ee3"] == item["true"]:
            winner = "Ee3"
        else:
            winner = "neither"
        print(
            f"Trial #{item['id']}: true={item['true']} | "
            f"Ee3={item['ee3']} | e3={item['e3']} | winner={winner}"
        )


if __name__ == "__main__":
    main()
