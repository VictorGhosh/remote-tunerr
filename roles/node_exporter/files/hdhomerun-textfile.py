#!/usr/bin/python3
# Managed by Ansible. Writes HDHomeRun tuner status for node_exporter's textfile collector.
# Usage: hdhomerun-textfile.py http://<tuner-ip>/status.json
import json
import os
import sys
import urllib.request

OUT = "/var/lib/prometheus/node-exporter/hdhomerun.prom"

GAUGES = {
    "SignalStrengthPercent": "hdhomerun_tuner_signal_strength_percent",
    "SignalQualityPercent": "hdhomerun_tuner_signal_quality_percent",
    "SymbolQualityPercent": "hdhomerun_tuner_symbol_quality_percent",
    "NetworkRate": "hdhomerun_tuner_network_rate_bits",
}


def main():
    lines = []
    try:
        with urllib.request.urlopen(sys.argv[1], timeout=5) as resp:
            tuners = json.load(resp)
        lines.append("hdhomerun_up 1")
    except (OSError, ValueError):
        tuners = []
        lines.append("hdhomerun_up 0")

    for t in tuners:
        tuner = t["Resource"]
        active = 1 if "VctNumber" in t else 0
        lines.append(f'hdhomerun_tuner_active{{tuner="{tuner}"}} {active}')
        if not active:
            continue
        labels = f'tuner="{tuner}",channel="{t["VctNumber"]}",name="{t.get("VctName", "")}"'
        for field, metric in GAUGES.items():
            if field in t:
                lines.append(f"{metric}{{{labels}}} {t[field]}")

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
