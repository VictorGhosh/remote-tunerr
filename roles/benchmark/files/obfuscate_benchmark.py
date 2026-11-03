#!/usr/bin/env python3
"""Strip location-identifying data from a remote-tuner benchmark result."""
import argparse
import json
import re
import sys
from pathlib import Path

# Keys whose values are channel numbers: replaced with stable placeholders.
CHANNEL_KEYS = {"channel", "channels", "guidenumber"}
# Keys whose values are always removed outright.
SENSITIVE_KEYS = {"guidename", "url", "tuner_ip", "pi_ip"}
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


class Censor:
    def __init__(self):
        self.labels = {}

    def channel(self, value) -> str:
        key = str(value)
        if key not in self.labels:
            self.labels[key] = f"censored-{len(self.labels) + 1}"
        return self.labels[key]


def scrub(node, censor: Censor, key: str = ""):
    k = key.lower()
    if isinstance(node, dict):
        return {name: scrub(value, censor, name) for name, value in node.items()}
    if isinstance(node, list):
        return [scrub(item, censor, key) for item in node]
    if k in CHANNEL_KEYS:
        return censor.channel(node)
    if k in SENSITIVE_KEYS:
        return "censored"
    if isinstance(node, str):
        return IPV4.sub("censored", node)
    return node


def main():
    parser = argparse.ArgumentParser(description="Remove location-identifying data from benchmark results.")
    parser.add_argument("results", type=Path, help="benchmark results file (e.g. results.json)")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: <name>.obfuscated.json)")
    args = parser.parse_args()

    src = args.results
    dst = args.output or src.with_name(f"{src.stem}.obfuscated.json")
    if dst.resolve() == src.resolve():
        sys.exit("refusing to overwrite the original results; pick a different output file")

    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    censor = Censor()
    clean = scrub(data, censor)

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=4)
        f.write("\n")

    print(f"wrote {dst} ({len(censor.labels)} channels censored)")

    lineup = src.with_name("lineup.json")
    if lineup.exists():
        print(f"note: {lineup} has station names and the tuner's IP; keep it out of git", file=sys.stderr)


if __name__ == "__main__":
    main()
