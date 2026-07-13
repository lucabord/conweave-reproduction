#!/usr/bin/env python3
"""Reproduce ConWeave paper Figure 14 (report Figure 10).

Produces two kinds of CDF plots from the raw NS-3 runs:
  (a) reorder-VOQ memory usage (packets) per ToR switch (ConWeave only);
  (b) uplink throughput imbalance (MAX-MIN)/AVG per switch, computed over
      100 us windows - same algorithm as the authors' analysis/plot_uplink.py,
      one figure per flow-control mode (Lossless, IRN) with all four schemes.

Usage (defaults match this repo's layout; simulations must have been run
first, see README step 3):

    python3 reproduce_fig14.py \
        --data_dir <ns-3.19>/mix/output \
        --history  <ns-3.19>/mix/.history \
        --output_dir ../figures \
        --netload 50

Instead of taking config ids on the command line, the script selects the
*baseline* run for each (flow control, scheme) automatically from .history:
topology leaf_spine_128_100G_OS2 at the requested load, 9 MB buffer,
default VOQ waiting time (200 us), no ablation flags, and a complete FCT log
(>= 900k lines, i.e. the run was not cut short).

Per selected run it reads, from mix/output/<cid>/:
  - config.txt              run parameters (to verify buffer/ablation);
  - <cid>_out_fct.txt       per-flow FCT log (only to check completeness);
  - <cid>_out_voq_cdf.txt   precomputed VOQ-occupancy CDF ($1 = packets,
                            $4 = cumulative fraction), plot (a);
  - <cid>_out_uplink.txt    uplink byte counters "ts,switch,port,txBytes"
                            sampled periodically, plot (b).
"""

import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FC_COLORS = {"Lossless": "tab:blue", "IRN": "tab:orange"}
FC_STYLES = {"Lossless": "solid", "IRN": "dashed"}
LB_MODES = {0: "ECMP", 3: "CONGA", 6: "LetFlow", 9: "ConWeave"}
LB_ORDER = ["ECMP", "CONGA", "LetFlow", "ConWeave"]
LB_COLORS = {"ECMP": "tab:green", "CONGA": "tab:blue",
             "LetFlow": "tab:purple", "ConWeave": "tab:orange"}
LB_STYLES = {"ECMP": "dashed", "CONGA": "dashdot",
             "LetFlow": "dotted", "ConWeave": "solid"}
TOPO = "leaf_spine_128_100G_OS2"
COMPLETE_FCT_LINES = 900000


def find_baseline_runs(history_file, data_dir, netload):
    """Map flow control -> {lb_name: baseline config id}.

    .history is a CSV with one line per launched run; the fields used here:
    [1] config id, [3] load-balancer code, [8] ConWeave VOQ waiting time (us),
    [9]/[10] PFC/IRN flags, [16] network load (%).
    """
    runs = {}
    with open(history_file) as f:
        for line in f:
            p = line.strip().split(",")
            if len(p) < 18 or TOPO not in line:
                continue
            lb = LB_MODES.get(int(p[3]))
            if lb is None or p[16] != netload:
                continue
            if lb == "ConWeave" and p[8] != "200":  # keep default VOQ wait only
                continue
            fc = {("1", "0"): "Lossless", ("0", "1"): "IRN"}.get((p[9], p[10]))
            if fc is None:
                continue
            cid = p[1]
            cfg = os.path.join(data_dir, cid, "config.txt")
            fct = os.path.join(data_dir, cid, f"{cid}_out_fct.txt")
            if not (os.path.exists(cfg) and os.path.exists(fct)):
                continue
            with open(cfg) as fc_file:
                cfg_text = fc_file.read()
            if "BUFFER_SIZE 9\n" not in cfg_text:  # baseline buffer only
                continue
            if "CONWEAVE_DISABLE_REORDER 1" in cfg_text:  # skip ablation runs
                continue
            with open(fct) as ff:
                if sum(1 for _ in ff) < COMPLETE_FCT_LINES:  # incomplete run
                    continue
            runs.setdefault(fc, {})[lb] = cid
    return runs


def read_voq_cdf(path):
    """Read the simulator's precomputed VOQ CDF: column 1 = occupancy in
    packets, column 4 = cumulative fraction of samples."""
    xs, ys = [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            xs.append(float(p[0]))
            ys.append(float(p[3]))
    return xs, ys


def uplink_imbalance_cdf(path, t_start, t_end, interval=100000):
    """Per-switch uplink imbalance CDF, same algorithm as plot_uplink.py.

    The uplink log holds cumulative tx-byte counters per (switch, port),
    sampled periodically. Steps:
      1. keep one sample per `interval` ns (100 us windows) inside
         [t_start, t_end];
      2. difference consecutive samples -> bytes sent per port per window;
      3. per switch and window, imbalance = (MAX-MIN)/AVG across its
         uplink ports, in %; idle windows (AVG = 0) are skipped;
      4. pool all (switch, window) values into one sorted CDF.
    """
    history, diffs = {}, {}   # last counter and per-window deltas, per port
    last_ts = 0
    with open(path) as f:
        for line in f:
            ts, swid, port, val = line.strip().split(",")
            ts, val = int(ts), int(val)
            if ts < t_start or ts > t_end:
                continue
            # accept only the first sample of each 100 us window
            if last_ts == 0 or last_ts + interval <= ts:
                last_ts = ts
            elif last_ts != ts:
                continue
            key = (int(swid), int(port))
            if key in history:
                diffs.setdefault(key, []).append(val - history[key])
            history[key] = val

    # group the per-port series by switch: rows = ports, columns = windows
    by_switch = {}
    for (swid, _), v in diffs.items():
        by_switch.setdefault(swid, []).append(v)

    vals = []
    for vecs in by_switch.values():
        for window in np.array(vecs).T:   # one column = one time window
            if np.average(window) == 0:
                continue
            vals.append((np.max(window) - np.min(window)) / np.average(window) * 100)

    v = np.sort(vals)
    p = np.arange(1, len(v) + 1) / len(v)
    return v, p


def main():
    ap = argparse.ArgumentParser(description="Reproduce ConWeave Figure 14")
    ap.add_argument("--data_dir", default="../../ns-allinone-3.19/ns-3.19/mix/output")
    ap.add_argument("--history", default="../../ns-allinone-3.19/ns-3.19/mix/.history")
    ap.add_argument("--output_dir", default="../figures")
    ap.add_argument("--netload", default="50", choices=("50", "80"),
                    help="network load (%%) of the runs to plot")
    # measurement window (ns): skip warm-up, stop before cool-down
    ap.add_argument("--sT", type=int, default=2005000000)
    ap.add_argument("--fT", type=int, default=2100000000)
    args = ap.parse_args()

    here = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(here, args.data_dir) if not os.path.isabs(args.data_dir) else args.data_dir
    history = os.path.join(here, args.history) if not os.path.isabs(args.history) else args.history
    out_dir = os.path.join(here, args.output_dir) if not os.path.isabs(args.output_dir) else args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    runs = find_baseline_runs(history, data_dir, args.netload)
    if not runs:
        sys.exit("ERROR: no baseline runs found.")
    for fc, by_lb in runs.items():
        print(f"baseline {fc}: {by_lb}")

    # (a) VOQ memory usage CDF (ConWeave only: other schemes have no VOQs)
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    for fc in ("Lossless", "IRN"):
        cid = runs.get(fc, {}).get("ConWeave")
        if cid is None:
            continue
        xs, ys = read_voq_cdf(os.path.join(data_dir, cid, f"{cid}_out_voq_cdf.txt"))
        ax.plot(xs, ys, color=FC_COLORS[fc], linestyle=FC_STYLES[fc],
                linewidth=2.5, label=fc)
        print(f"  {fc}: median<= {next(x for x, y in zip(xs, ys) if y >= 0.5):.0f} pkts, "
              f"p99<= {next(x for x, y in zip(xs, ys) if y >= 0.99):.0f} pkts, max {xs[-1]:.0f} pkts")
    ax.set_xlabel("ConWeave reorder-queue memory usage (packets)", fontsize=12)
    ax.set_ylabel("CDF", fontsize=12)
    ax.set_title(f"Reorder-queue memory per ToR ({args.netload}% load)",
                 fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(which="major", alpha=0.3, linestyle="--")
    ax.legend(loc="lower right", frameon=False, fontsize=11)
    fig.tight_layout()
    path = os.path.join(
        out_dir, f"fig14_queue_cdf_{TOPO}_load{args.netload}.png")
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"saved {os.path.basename(path)}")
    plt.close()

    # (b) uplink throughput-imbalance CDF, one figure per flow control,
    # all four schemes (paper Figure 14(a); DRILL omitted — never simulated)
    for fc in ("Lossless", "IRN"):
        if fc not in runs:
            continue
        fig, ax = plt.subplots(figsize=(6.0, 3.5))
        for lb in LB_ORDER:
            cid = runs[fc].get(lb)
            if cid is None:
                continue
            v, p = uplink_imbalance_cdf(
                os.path.join(data_dir, cid, f"{cid}_out_uplink.txt"), args.sT, args.fT)
            ax.plot(v, p, color=LB_COLORS[lb], linestyle=LB_STYLES[lb],
                    linewidth=2.5, label=lb)
            print(f"  {fc}/{lb}: uplink imbalance median {np.median(v):.0f}%, "
                  f"p99 {np.percentile(v, 99):.0f}%")
        ax.set_xlabel("Throughput imbalance (MAX−MIN)/AVG (%)", fontsize=12)
        ax.set_ylabel("CDF", fontsize=12)
        ax.set_title(f"Uplink throughput imbalance ({fc}, {args.netload}% load)",
                     fontsize=12, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(which="major", alpha=0.3, linestyle="--")
        ax.legend(loc="lower right", frameon=False, fontsize=11)
        fig.tight_layout()
        path = os.path.join(
            out_dir, f"fig14_uplink_cdf_{fc}_{TOPO}_load{args.netload}.png")
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
        print(f"saved {os.path.basename(path)}")
        plt.close()


if __name__ == "__main__":
    main()
