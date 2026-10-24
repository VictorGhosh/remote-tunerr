import json
import time
import shutil
import socket
import argparse
import threading
import subprocess
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description="Benchmark a remote HDHomeRun the way Plex uses it.")
parser.add_argument("tuner_ip")
parser.add_argument("pi_ip", help="tuner Pi address running iperf3 -s")
parser.add_argument("channels", nargs="*", help="up to 4 guide numbers; picked automatically if omitted")
ARGS = parser.parse_args()

STREAM_SECONDS = 300
PAUSE_SECONDS = 60
MAX_STREAMS = 4


def get_channels() -> list[dict]:
    with urllib.request.urlopen(f"http://{ARGS.tuner_ip}/lineup.json") as r:
        lineup = json.load(r)

    with open("lineup.json", "w", encoding="utf-8") as f:
        json.dump(lineup, f, indent=4)

    return lineup


def pick_channels(lineup: list[dict]) -> list[str]:
    # One subchannel per station so every stream needs its own tuner
    picked = {}

    for ch in lineup:
        station = ch["GuideNumber"].split(".")[0]
        picked.setdefault(station, ch["GuideNumber"])

    return list(picked.values())[:MAX_STREAMS]


def pretest() -> dict:
    # Latency a TCP connect like ping.
    times = []
    for _ in range(10):
        start = time.monotonic()
        socket.create_connection((ARGS.tuner_ip, 80), timeout=5).close()
        times.append((time.monotonic() - start) * 1000)
        time.sleep(0.2)

    # Bandwidth -R Pi send to tester should be  same direction as streams -J for JSON output
    out = subprocess.run(["iperf3", "-c", ARGS.pi_ip, "-R", "-t", "10", "-J"], capture_output=True, text=True, check=True)
    bps = json.loads(out.stdout)["end"]["sum_received"]["bits_per_second"]

    result = {
        "latency_ms_min": round(min(times), 1),
        "latency_ms_avg": round(sum(times) / len(times), 1),
        "latency_ms_max": round(max(times), 1),
        "bandwidth_mbps": round(bps / 1e6, 1),
    }
    print(f"pretest: latency {result['latency_ms_min']}/{result['latency_ms_avg']}/{result['latency_ms_max']} ms "
          f"(min/avg/max), bandwidth {result['bandwidth_mbps']} Mbps")
    return result


def record_stream(guide_number: str, ts_file: Path):
    url = f"http://{ARGS.tuner_ip}:5004/auto/v{guide_number}?duration={STREAM_SECONDS}"

    with urllib.request.urlopen(url, timeout=10) as r, open(ts_file, "wb") as f:
        shutil.copyfileobj(r, f)


def analyze(ts_file: Path) -> dict:
    # MPEG-TS: 188-byte packets. Each PID has a 4-bit counter that goes up by 1 per packet
    # a jump means packets were lost.
    packets = sync_errors = transport_errors = discontinuities = 0
    last_cc = {}

    with open(ts_file, "rb") as f:
        while block := f.read(188 * 1000):
            for i in range(0, len(block) - 187, 188):
                pkt = block[i:i + 188]
                packets += 1

                if pkt[0] != 0x47: # every packet starts with sync byte 0x47
                    sync_errors += 1
                    continue
                if pkt[1] & 0x80: # transport_error_indicator: tuner saw a bad packet
                    transport_errors += 1

                pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
                if pid == 0x1FFF: # null packets have no counter
                    continue

                cc = pkt[3] & 0x0F
                has_payload = pkt[3] & 0x10
                if pid in last_cc and has_payload:
                    if cc not in ((last_cc[pid] + 1) % 16, last_cc[pid]): # a repeat is allowed
                        discontinuities += 1
                last_cc[pid] = cc

    return {
        "packets": packets,
        "sync_errors": sync_errors,
        "transport_errors": transport_errors,
        "discontinuities": discontinuities,
    }


def run_round(channels: list[str], n: int) -> list[dict]:
    print(f"round {n}: {n} stream(s)")
    files = {gn: Path(f"{n}streams_{gn}.ts") for gn in channels[:n]}

    threads = [threading.Thread(target=record_stream, args=(gn, ts_file)) for gn, ts_file in files.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results = []
    for gn, ts_file in files.items():
        result = {"streams": n, "channel": gn}

        if ts_file.exists():
            result["mbps"] = round(ts_file.stat().st_size * 8 / STREAM_SECONDS / 1e6, 2)
            result.update(analyze(ts_file))
            ts_file.unlink()
            print(f"  {gn:>6}  {result['mbps']:5.2f} Mbps  {result['packets']:>8} packets  "
                  f"sync {result['sync_errors']}  transport {result['transport_errors']}  "
                  f"discontinuities {result['discontinuities']}")
        else:
            result["error"] = "no data"
            print(f"  {gn:>6}  no data")

        results.append(result)

    return results


def main():
    lineup = get_channels()
    channels = ARGS.channels[:MAX_STREAMS] or pick_channels(lineup)
    print(f"channels: {' '.join(channels)}")
    pre = pretest()

    rounds = []
    for n in range(1, len(channels) + 1):
        time.sleep(PAUSE_SECONDS)
        rounds += run_round(channels, n)

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump({"channels": channels, "pretest": pre, "rounds": rounds}, f, indent=4)

    errors = sum(r.get("sync_errors", 0) + r.get("transport_errors", 0) + r.get("discontinuities", 0) for r in rounds)
    missing = sum(1 for r in rounds if "error" in r)
    print(f"done: {len(rounds)} streams, {errors} errors, {missing} without data")


if __name__ == '__main__':
    main()
