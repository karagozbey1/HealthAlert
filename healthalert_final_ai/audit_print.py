import json
c = json.load(open("outputs/hybrid_redesign/audit/dataset_contract.json"))
for d in c["datasets"]:
    status = d["task_routing"]["fall_detection"]["status"]
    wind = int(d.get("windowed_exists", False))
    splits = int(d.get("splits_exist", False))
    modalities = d.get("modalities", [])
    print(f"{d['dataset']:<32} fall={status:<10} wind={wind} splits={splits} mod={modalities}")
