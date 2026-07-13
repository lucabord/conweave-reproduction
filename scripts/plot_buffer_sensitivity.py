#!/usr/bin/env python3
"""
Standalone plotter for the buffer-size sensitivity figures (report S5.1).

Reads the raw NS-3 runs of the buffer sweep and produces
buffer_sensitivity_fct.{png,pdf} and buffer_sensitivity_breakdown.{png,pdf}:

    python3 plot_buffer_sensitivity.py \
        --data_dir <ns-3.19>/mix/output \
        --history  <ns-3.19>/mix/.history_buffer_full \
        --output_dir ../figures

Inputs:
  - the artifact's `.history` CSV (one line per launched run; field 1 is the
    config id, field 3 the load-balancer code, field 13 the topology);
  - per run, `mix/output/<cid>/config.txt` (to read BUFFER_SIZE) and
    `mix/output/<cid>/<cid>_out_fct.txt`, the per-flow FCT log whose columns
    are: $5 = flow size (bytes), $6 = start time (ns), $7 = actual FCT (ns),
    $8 = standalone FCT (ns, same flow on an empty network).
"""

import os
import sys
import argparse
import subprocess
import numpy as np
import matplotlib.pyplot as plt

# Load-balancer codes used in .history; the sweep only ran these two schemes.
LB_MODES = {0: "ECMP", 9: "ConWeave"}
# Bandwidth-delay product (bytes) of the sweep topology: flows >= 1 BDP are
# classified as "large" in the breakdown plot.
TOPO_BDP = {"leaf_spine_128_100G_OS2": 104000}
CW_COLOR, ECMP_COLOR = "#FF9800", "#4CAF50"


# =============================================================================
# Parse raw run data (identical conventions to the report:
# measurement window [sT, fT], slowdown = max(1, actual/standalone FCT),
# large flow = size >= 1 BDP)
# =============================================================================

def parse_fct_summary(fct_file, t0, t1, bdp):
    # awk keeps only flows fully inside the window and prints "slowdown size".
    cmd = (f"awk '{{ if ($6>{t0} && $6+$7<{t1}) "
           f"{{ slow=$7/$8; s=(slow<1?1:slow); print s, $5 }} }}' {fct_file}")
    try:
        out = subprocess.check_output(cmd, shell=True).decode()
    except subprocess.CalledProcessError:
        return None
    lines = [l for l in out.strip().split("\n") if l.strip()]
    if len(lines) < 20:
        return None
    allv, small, large = [], [], []
    for ln in lines:
        s, sz = ln.split()
        s, sz = float(s), int(sz)
        allv.append(s)
        (small if sz < bdp else large).append(s)
    r = {"all_avg": float(np.mean(allv)),
         "all_p99": float(np.percentile(allv, 99))}
    if small:
        r["small_avg"] = float(np.mean(small))
    if large:
        r["large_avg"] = float(np.mean(large))
        r["large_p99"] = float(np.percentile(large, 99))
    return r


def parse_history(history_file):
    """Return the sweep's runs as {cid, lb, topo}, skipping anything else."""
    entries = []
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("./waf"):
                continue
            p = line.split(",")
            if len(p) < 14 or not any(t in line for t in TOPO_BDP):
                continue
            lb = LB_MODES.get(int(p[3]))
            if lb is None:
                continue
            entries.append({"cid": p[1], "lb": lb, "topo": p[13]})
    return entries


def buffer_of(data_dir, cid):
    """Read the swept parameter (BUFFER_SIZE, MB) from the run's config."""
    cfg = os.path.join(data_dir, cid, "config.txt")
    if not os.path.exists(cfg):
        return None
    with open(cfg) as f:
        for line in f:
            if line.startswith("BUFFER_SIZE"):
                return int(line.split()[1])
    return None


def load_from_runs(data_dir, history, t0, t1):
    cw, ecmp = {}, {}
    for e in parse_history(history):
        bdp = TOPO_BDP.get(e["topo"], 104000)
        buf = buffer_of(data_dir, e["cid"])
        fct = os.path.join(data_dir, e["cid"], f"{e['cid']}_out_fct.txt")
        if buf is None or not os.path.exists(fct):
            continue
        st = parse_fct_summary(fct, t0, t1, bdp)
        if st is None:
            continue
        (cw if e["lb"] == "ConWeave" else ecmp)[buf] = st
        print(f"  {e['lb']:9s} buf={buf:2d}MB  avg={st['all_avg']:.3f} "
              f"p99={st['all_p99']:.3f}")
    return cw, ecmp


# =============================================================================
# The plots (same style as the report figures)
# =============================================================================

def plot(cw, ecmp, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    if not cw:
        sys.exit("ERROR: no ConWeave data points found.")
    bufs, ebufs = sorted(cw), sorted(ecmp)

    #Figure 1: avg & p99 vs buffer size, with the 9 MB reference line
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))
    ax1.plot(bufs, [cw[b]["all_avg"] for b in bufs], "D-", color=CW_COLOR,
             lw=2, ms=6, label="ConWeave")
    if ebufs:
        ax1.plot(ebufs, [ecmp[b]["all_avg"] for b in ebufs], "o--",
                 color=ECMP_COLOR, lw=2, ms=6, label="ECMP")
    ax1.set_xlabel("Switch Buffer Size (MB)", fontsize=12)
    ax1.set_ylabel("Average FCT Slowdown", fontsize=12)
    ax1.set_title("Avg FCT Slowdown vs Buffer Size", fontsize=12)
    ax1.axvline(9, color="gray", ls=":", lw=1)
    ax1.text(9.2, ax1.get_ylim()[1], "paper default", fontsize=8,
             va="top", color="gray")

    ax2.plot(bufs, [cw[b]["all_p99"] for b in bufs], "D-", color=CW_COLOR,
             lw=2, ms=6, label="ConWeave")
    if ebufs:
        ax2.plot(ebufs, [ecmp[b]["all_p99"] for b in ebufs], "o--",
                 color=ECMP_COLOR, lw=2, ms=6, label="ECMP")
    ax2.set_xlabel("Switch Buffer Size (MB)", fontsize=12)
    ax2.set_ylabel("p99 FCT Slowdown", fontsize=12)
    ax2.set_title("p99 FCT Slowdown vs Buffer Size", fontsize=12)
    ax2.axvline(9, color="gray", ls=":", lw=1)

    for ax in (ax1, ax2):
        ax.legend(frameon=False, fontsize=10)
        ax.grid(alpha=0.3, ls="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(bottom=1)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(output_dir, f"buffer_sensitivity_fct.{ext}"),
                    dpi=300, bbox_inches="tight")
    print("  saved buffer_sensitivity_fct.png / .pdf")
    plt.close()

    #Figure 2: small/large breakdown + gain over ECMP
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))
    if any("small_avg" in cw[b] for b in bufs):
        ax1.plot(bufs, [cw[b].get("small_avg", np.nan) for b in bufs], "s-",
                 color="#2196F3", lw=2, ms=6, label="small avg")
        ax1.plot(bufs, [cw[b].get("large_avg", np.nan) for b in bufs], "^-",
                 color="#F44336", lw=2, ms=6, label="large avg")
        ax1.plot(bufs, [cw[b].get("large_p99", np.nan) for b in bufs], "^--",
                 color="#F44336", lw=2, ms=6, alpha=0.6, label="large p99")
    ax1.set_xlabel("Switch Buffer Size (MB)", fontsize=12)
    ax1.set_ylabel("FCT Slowdown", fontsize=12)
    ax1.set_title("ConWeave: small vs large flows", fontsize=12)
    ax1.legend(frameon=False, fontsize=9)
    ax1.grid(alpha=0.3, ls="--")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.set_ylim(bottom=1)

    common = sorted(set(bufs) & set(ebufs))
    if common:
        imp_avg = [(ecmp[b]["all_avg"] - cw[b]["all_avg"]) / ecmp[b]["all_avg"] * 100
                   for b in common]
        imp_p99 = [(ecmp[b]["all_p99"] - cw[b]["all_p99"]) / ecmp[b]["all_p99"] * 100
                   for b in common]
        xx = np.arange(len(common))
        ax2.bar(xx - 0.2, imp_avg, 0.35, color=CW_COLOR, alpha=0.85, label="avg gain")
        ax2.bar(xx + 0.2, imp_p99, 0.35, color=CW_COLOR, alpha=0.4, hatch="//",
                label="p99 gain")
        ax2.set_xticks(xx)
        ax2.set_xticklabels([f"{b}MB" for b in common])
        ax2.axhline(0, color="black", lw=0.5)
        ax2.set_xlabel("Switch Buffer Size", fontsize=12)
        ax2.set_ylabel("Improvement over ECMP (%)", fontsize=12)
        ax2.set_title("ConWeave gain vs ECMP", fontsize=12)
        ax2.legend(frameon=False, fontsize=10)
        ax2.grid(axis="y", alpha=0.3, ls="--")
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(output_dir,
                                 f"buffer_sensitivity_breakdown.{ext}"),
                    dpi=300, bbox_inches="tight")
    print("  saved buffer_sensitivity_breakdown.png / .pdf")
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="Standalone buffer-sensitivity plotter")
    ap.add_argument("--data_dir", required=True, help="mix/output dir with raw runs")
    ap.add_argument("--history", required=True, help="mix/.history file")
    ap.add_argument("--output_dir", default=".")
    ap.add_argument("--sT", type=int, default=2005000000)
    ap.add_argument("--fT", type=int, default=2150000000)
    args = ap.parse_args()

    cw, ecmp = load_from_runs(args.data_dir, args.history, args.sT, args.fT)
    plot(cw, ecmp, args.output_dir)


if __name__ == "__main__":
    main()
