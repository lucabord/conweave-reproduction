#!/usr/bin/env python3
"""
Reproduce Figure 13 from ConWeave (SIGCOMM'23).

Figure 13 zooms in on *large* flows (size >= 1 BDP). It reports the FCT
slowdown distribution for large flows across the load-balancing schemes,
which is where reordering hurts RDMA the most. We render it two ways:
  (a) a CDF of large-flow FCT slowdown per scheme, and
  (b) a grouped bar chart of avg / p99 large-flow slowdown per scheme.

Both are driven by the same raw `*_out_fct.txt` files and `mix/.history`
index as Figure 12.

Usage:
    python3 reproduce_fig13.py \
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

LB_MODES = {0: "ECMP", 2: "DRILL", 3: "CONGA", 6: "LetFlow", 9: "ConWeave"}
LB_COLORS = {
    "ECMP": "#4CAF50", "CONGA": "#2196F3", "LetFlow": "#9C27B0",
    "ConWeave": "#FF9800", "DRILL": "#F44336",
}
LB_LS = {"ECMP": "-", "CONGA": "--", "LetFlow": "-.", "ConWeave": "-", "DRILL": ":"}
LB_ORDER = ["ECMP", "CONGA", "LetFlow", "ConWeave"]
TOPO_BDP = {"leaf_spine_128_100G_OS2": 104000, "fat_k8_100G_OS2": 156000}


def parse_history(history_file):
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


def parse_slowdown(filename, t0, t1, bdp, large=True):
    """Large flows: size >= bdp. Small flows: size < bdp."""
    cmp_op = ">=" if large else "<"
    # ternary assigned to a variable -> portable across gawk and BSD awk
    cmd = (
        f"cat {filename} | awk '{{ if ($6>{t0} && $6+$7<{t1} && $5{cmp_op}{bdp}) "
        f"{{ slow=$7/$8; s=(slow<1?1:slow); print s }} }}' | sort -n"
    )
    try:
        out = subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        return None
    vals = [float(x) for x in out.strip().split("\n") if x.strip()]
    return vals if len(vals) >= 5 else None


def stats(vals):
    a = np.array(vals)
    return {
        "avg": float(np.mean(a)), "median": float(np.median(a)),
        "p95": float(np.percentile(a, 95)), "p99": float(np.percentile(a, 99)),
        "p999": float(np.percentile(a, 99.9)), "n": len(a),
    }


def plot_cdf(data, title, filename, output_dir):
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    for lb in LB_ORDER:
        if lb not in data:
            continue
        v = np.sort(data[lb])
        cdf = np.arange(1, len(v) + 1) / len(v)
        ax.plot(v, cdf, color=LB_COLORS[lb], linestyle=LB_LS[lb], linewidth=2.0, label=lb)
    ax.set_xlabel("Large-flow FCT Slowdown", fontsize=12)
    ax.set_ylabel("CDF", fontsize=12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, 1.02)
    ax.set_xlim(left=1)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    ax.grid(alpha=0.3, linestyle="--")
    fig.tight_layout()
    path = os.path.join(output_dir, filename)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"  saved {filename}")
    plt.close()


def plot_bar(st, title, filename, output_dir):
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    lbs = [lb for lb in LB_ORDER if lb in st]
    x = np.arange(len(lbs))
    w = 0.35
    avg = [st[lb]["avg"] for lb in lbs]
    p99 = [st[lb]["p99"] for lb in lbs]
    cols = [LB_COLORS[lb] for lb in lbs]
    b1 = ax.bar(x - w/2, avg, w, color=cols, alpha=0.85, edgecolor="black",
                linewidth=0.5, label="Average")
    b2 = ax.bar(x + w/2, p99, w, color=cols, alpha=0.4, edgecolor="black",
                linewidth=0.5, hatch="//", label="p99")
    ax.set_xlabel("Load-balancing scheme", fontsize=12)
    ax.set_ylabel("Large-flow FCT Slowdown", fontsize=12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(lbs, fontsize=10)
    ax.legend(frameon=False, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.2f}", xy=(bar.get_x() + bar.get_width()/2, h),
                        xytext=(0, 2), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    path = os.path.join(output_dir, filename)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"  saved {filename}")
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="Reproduce ConWeave Figure 13")
    ap.add_argument("--data_dir", default="../../conweave-ns3/mix/output")
    ap.add_argument("--history", default="../../conweave-ns3/mix/.history")
    ap.add_argument("--output_dir", default="../figures")
    ap.add_argument("--sT", type=int, default=2005000000)
    ap.add_argument("--fT", type=int, default=2150000000)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    if not os.path.exists(args.history):
        sys.exit(f"ERROR: history not found: {args.history}")

    mapping = parse_history(args.history)
    for (topo, load, fc), runs in mapping.items():
        bdp = TOPO_BDP.get(topo, 104000)
        print(f"\n=== topo={topo} load={load}% fc={fc} 1BDP={bdp} ===")
        large, st = {}, {}
        for cid, lb in runs:
            fct = os.path.join(args.data_dir, cid, f"{cid}_out_fct.txt")
            if not os.path.exists(fct):
                print(f"  WARNING: missing FCT for {lb}")
                continue
            v = parse_slowdown(fct, args.sT, args.fT, bdp, large=True)
            if v:
                large[lb] = v
                st[lb] = stats(v)
                print(f"  {lb:9s}: {st[lb]['n']:6d} large flows  "
                      f"avg={st[lb]['avg']:.3f}  p99={st[lb]['p99']:.3f}")
        if not large:
            continue
        plot_cdf(large, f"Large-flow FCT Slowdown CDF ({fc}, {load}%)",
                 f"fig13_large_cdf_{fc}_{topo}_load{load}.png", args.output_dir)
        plot_bar(st, f"Large-flow FCT Slowdown ({fc}, {load}%)",
                 f"fig13_large_bar_{fc}_{topo}_load{load}.png", args.output_dir)

        print(f"\n  {'Scheme':<10}{'N':>8}{'Avg':>9}{'Med':>9}{'p95':>9}{'p99':>9}{'p99.9':>9}")
        print("  " + "-" * 62)
        for lb in LB_ORDER:
            if lb in st:
                s = st[lb]
                print(f"  {lb:<10}{s['n']:>8}{s['avg']:>9.3f}{s['median']:>9.3f}"
                      f"{s['p95']:>9.3f}{s['p99']:>9.3f}{s['p999']:>9.3f}")
    print("\nDone. Figures in", args.output_dir)


if __name__ == "__main__":
    main()
