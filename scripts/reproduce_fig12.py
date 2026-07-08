#!/usr/bin/env python3
"""
Reproduce Figure 12 from ConWeave (SIGCOMM'23).

Figure 12 reports the *average* and *99th-percentile* FCT slowdown as a
function of flow size, for four load-balancing schemes (ECMP, CONGA,
LetFlow, ConWeave) under two flow-control modes (Lossless RDMA with PFC,
and IRN). The network runs at 50% load on a 128-server leaf-spine fabric.

The script reads the raw per-flow FCT files produced by the NS-3 simulator
(`*_out_fct.txt`) and the run index (`mix/.history`), groups runs by
(topology, load, flow-control), and produces one Avg and one p99 plot per
group.

FCT file columns (whitespace separated):
    $1 sip  $2 dip  $3 sport  $4 dport  $5 size(B)  $6 start(ns)
    $7 fct(ns)  $8 standalone_fct(ns)  ...
FCT slowdown = fct / standalone_fct  (clamped to >= 1).

Usage:
    python3 reproduce_fig12.py \
        --data_dir ../../conweave-ns3/mix/output \
        --history  ../../conweave-ns3/mix/.history \
        --output_dir ../figures
"""

import os
import sys
import argparse
import subprocess
import numpy as np
import matplotlib.pyplot as plt

# ── Mode mappings (match run.py / plot_fct.py in the artifact) ──────────────
LB_MODES = {0: "ECMP", 2: "DRILL", 3: "CONGA", 6: "LetFlow", 9: "ConWeave"}

LB_COLORS = {
    "ECMP": "#4CAF50", "CONGA": "#2196F3", "LetFlow": "#9C27B0",
    "ConWeave": "#FF9800", "DRILL": "#F44336",
}
LB_MARKERS = {"ECMP": "o", "CONGA": "s", "LetFlow": "^", "ConWeave": "D", "DRILL": "x"}
LB_ORDER = ["ECMP", "CONGA", "LetFlow", "ConWeave"]

# 1 BDP per topology (bytes) -- from run.py::topo2bdp
TOPO_BDP = {"leaf_spine_128_100G_OS2": 104000, "fat_k8_100G_OS2": 156000}


def get_pctl(sorted_arr, p):
    i = int(len(sorted_arr) * p)
    return sorted_arr[min(i, len(sorted_arr) - 1)]


def size2str(size_bytes):
    if size_bytes < 10000:
        return f"{size_bytes/1000:.1f}K"
    if size_bytes < 1000000:
        return f"{size_bytes/1000:.0f}K"
    return f"{size_bytes/1000000:.1f}M"


def parse_fct_file(filename, time_start, time_end, step=5):
    """Return per-flow-size-bucket slowdown statistics (avg, p99, ...)."""
    # NOTE: the ternary is assigned to a variable before `print` so the command
    # is portable between gawk (Linux/Docker) and BSD awk (macOS), which would
    # otherwise parse `print slow<1` as an output redirection.
    cmd = (
        f"cat {filename} | awk '{{ if ($6>{time_start} && $6+$7<{time_end}) "
        f"{{ slow=$7/$8; s=(slow<1?1:slow); print s, $5 }} }}' | sort -n -k 2"
    )
    try:
        out = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        print(f"  WARNING: could not parse {filename}")
        return None

    lines = [l for l in out.strip().split("\n") if l.strip()]
    n = len(lines)
    if n < 20:
        print(f"  WARNING: only {n} flows in {os.path.basename(filename)}")
        return None

    res = {"avg": [], "p99": [], "p95": [], "median": [], "size": [], "size_str": []}
    for i in range(0, 100, step):
        l_idx, r_idx = int(i * n / 100), int((i + step) * n / 100)
        bucket = lines[l_idx:r_idx]
        if not bucket:
            continue
        parsed = [[float(x.split()[0]), int(x.split()[1])] for x in bucket]
        slow = sorted(x[0] for x in parsed)
        res["size"].append(parsed[-1][1])
        res["size_str"].append(size2str(parsed[-1][1]))
        res["avg"].append(float(np.mean(slow)))
        res["median"].append(get_pctl(slow, 0.50))
        res["p95"].append(get_pctl(slow, 0.95))
        res["p99"].append(get_pctl(slow, 0.99))
    return res


def parse_history(history_file):
    """Map (topo, load, flow_control) -> [(config_id, lb_name)]."""
    mapping = {}
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("./waf"):
                continue
            p = line.split(",")
            if len(p) < 17 or not any(t in line for t in TOPO_BDP):
                continue
            lb_code, pfc, irn = int(p[3]), int(p[9]), int(p[10])
            topo, netload = p[13], p[16]
            if lb_code not in LB_MODES:
                continue
            if (pfc, irn) == (1, 0):
                fc = "Lossless"
            elif (pfc, irn) == (0, 1):
                fc = "IRN"
            else:
                continue
            mapping.setdefault((topo, netload, fc), []).append((p[1], LB_MODES[lb_code]))
    return mapping


def plot_metric(data_by_lb, metric, title, ylabel, filename, output_dir):
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    step = 5
    xvals = list(range(step, 100 + step, step))
    for lb in LB_ORDER:
        if lb not in data_by_lb:
            continue
        r = data_by_lb[lb]
        ax.plot(xvals[:len(r[metric])], r[metric], color=LB_COLORS[lb],
                marker=LB_MARKERS[lb], markersize=4, linewidth=2.0, label=lb)

    ax.set_xlabel("Flow Size", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ref = next((lb for lb in LB_ORDER if lb in data_by_lb), None)
    if ref and data_by_lb[ref]["size_str"]:
        labels = ["0"] + data_by_lb[ref]["size_str"]
        ticks = [0] + xvals
        ax.set_xticks(ticks[::2])
        ax.set_xticklabels(labels[::2], fontsize=9, rotation=40, ha="right")

    ax.set_ylim(bottom=1)
    ax.legend(loc="upper left", frameon=False, fontsize=10, ncol=2)
    ax.grid(which="major", alpha=0.3, linestyle="--")
    fig.tight_layout()

    path = os.path.join(output_dir, filename)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"  saved {filename}")
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="Reproduce ConWeave Figure 12")
    ap.add_argument("--data_dir", default="../../conweave-ns3/mix/output")
    ap.add_argument("--history", default="../../conweave-ns3/mix/.history")
    ap.add_argument("--output_dir", default="../figures")
    ap.add_argument("--sT", type=int, default=2005000000, help="start filter (ns)")
    ap.add_argument("--fT", type=int, default=2150000000,
                    help="end filter (ns); default fits a 0.1s run")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    if not os.path.exists(args.history):
        sys.exit(f"ERROR: history not found: {args.history}\nRun the simulations first.")

    mapping = parse_history(args.history)
    if not mapping:
        sys.exit("ERROR: no runs found in history.")

    print(f"Found {len(mapping)} experiment group(s).")
    for (topo, load, fc), runs in mapping.items():
        print(f"\n=== topo={topo} load={load}% fc={fc} ===")
        data = {}
        for cid, lb in runs:
            fct = os.path.join(args.data_dir, cid, f"{cid}_out_fct.txt")
            if not os.path.exists(fct):
                print(f"  WARNING: missing FCT for {lb} ({cid})")
                continue
            r = parse_fct_file(fct, args.sT, args.fT)
            if r:
                data[lb] = r
                print(f"  parsed {lb:9s} ({cid}) -> {len(r['avg'])} buckets")
        if not data:
            continue
        plot_metric(data, "avg", f"Avg FCT Slowdown ({fc}, {load}% load)",
                    "Average FCT Slowdown",
                    f"fig12_avg_{fc}_{topo}_load{load}.png", args.output_dir)
        plot_metric(data, "p99", f"p99 FCT Slowdown ({fc}, {load}% load)",
                    "99th-pctl FCT Slowdown",
                    f"fig12_p99_{fc}_{topo}_load{load}.png", args.output_dir)

    print("\nDone. Figures in", args.output_dir)


if __name__ == "__main__":
    main()
