#!/usr/bin/env python3
"""
Grey-Failure Sensitivity: ConWeave vs ECMP under per-link packet error rates.

Sweeps ERROR_RATE_PER_LINK over {0, 1e-6, 1e-5, 1e-4, 1e-3} and compares
ConWeave and ECMP FCT slowdown. The error rate models "grey failure": links
remain up but drop packets randomly (e.g., due to optics degradation or
thermal-induced BER).

Produces greyfailure_sensitivity.{png,pdf} and
greyfailure_large_flows.{png,pdf} (report S5.2), plus a summary table on
stdout (report Table 3).

Usage:
    python3 plot_greyfailure_sensitivity.py \
        --data_dir <ns-3.19>/mix/output \
        --history  <ns-3.19>/mix/.history_greyfailure \
        --output_dir ../figures \
        --sT 2005000000 --fT 2150000000

Inputs:
  - the artifact's `.history` CSV (one line per launched run; field 1 is the
    config id, field 3 the load-balancer code, field 13 the topology);
  - per run, `mix/output/<cid>/config.txt` (to read ERROR_RATE_PER_LINK) and
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
# Bandwidth-delay product (bytes): flows >= 1 BDP count as "large".
TOPO_BDP = {"leaf_spine_128_100G_OS2": 104000}
CW_COLOR, ECMP_COLOR = "#FF9800", "#4CAF50"


def parse_fct(fct_file, t0, t1, bdp):
    # awk keeps only flows fully inside the measurement window [t0, t1] and
    # prints "slowdown size", with slowdown = max(1, actual/standalone FCT).
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
    r = {
        "all_avg": float(np.mean(allv)),
        "all_p99": float(np.percentile(allv, 99)),
        "n_total": len(allv),
    }
    if small:
        r["small_avg"] = float(np.mean(small))
        r["small_p99"] = float(np.percentile(small, 99))
    if large:
        r["large_avg"] = float(np.mean(large))
        r["large_p99"] = float(np.percentile(large, 99))
    return r


def error_rate_of(data_dir, cid):
    """Read the swept parameter (ERROR_RATE_PER_LINK) from the run's config."""
    cfg = os.path.join(data_dir, cid, "config.txt")
    if not os.path.exists(cfg):
        return None
    with open(cfg) as f:
        for line in f:
            if line.startswith("ERROR_RATE_PER_LINK"):
                return float(line.split()[1])
    return None


def parse_history(history_file):
    """Return the sweep's runs as {cid, lb, topo}, skipping anything else."""
    entries = []
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("./waf"):
                continue
            p = line.split(",")
            if len(p) < 10 or not any(t in line for t in TOPO_BDP):
                continue
            lb_code = int(p[3])
            if lb_code not in LB_MODES:
                continue
            entries.append({"cid": p[1], "lb": LB_MODES[lb_code], "topo": p[13]})
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--sT", type=int, default=2005000000)
    ap.add_argument("--fT", type=int, default=2150000000)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    cw_results = {}   # error_rate -> stats
    ecmp_results = {}

    for e in parse_history(args.history):
        bdp = TOPO_BDP.get(e["topo"], 104000)
        err = error_rate_of(args.data_dir, e["cid"])
        fct = os.path.join(args.data_dir, e["cid"], f"{e['cid']}_out_fct.txt")
        if err is None or not os.path.exists(fct):
            print(f"  SKIP {e['cid']} ({e['lb']}): err={err}, fct exists={os.path.exists(fct)}")
            continue
        st = parse_fct(fct, args.sT, args.fT, bdp)
        if st is None:
            print(f"  SKIP {e['cid']} ({e['lb']}): too few flows")
            continue
        target = cw_results if e["lb"] == "ConWeave" else ecmp_results
        target[err] = st
        print(f"  {e['lb']:9s} err={err:.1e}  avg={st['all_avg']:.3f}  "
              f"p99={st['all_p99']:.3f}  large_avg={st.get('large_avg', float('nan')):.3f}  "
              f"n={st['n_total']}")

    if not cw_results:
        sys.exit("ERROR: no ConWeave grey-failure runs found.")

    # Sort by error rate; use small epsilon for 0.0 on log scale
    cw_rates = sorted(cw_results)
    ecmp_rates = sorted(ecmp_results)

    # For log-scale x-axis, replace 0.0 with a small value for display
    def logx(rates):
        return [r if r > 0 else 1e-8 for r in rates]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # Left: avg FCT slowdown
    ax = axes[0]
    ax.plot(logx(cw_rates), [cw_results[r]["all_avg"] for r in cw_rates],
            "D-", color=CW_COLOR, lw=2, ms=7, label="ConWeave")
    if ecmp_rates:
        ax.plot(logx(ecmp_rates), [ecmp_results[r]["all_avg"] for r in ecmp_rates],
                "o--", color=ECMP_COLOR, lw=2, ms=7, label="ECMP")
    ax.set_xscale("log")
    ax.set_xlabel("Per-Link Packet Error Rate", fontsize=12)
    ax.set_ylabel("Average FCT Slowdown", fontsize=12)
    ax.set_title("Avg FCT Slowdown vs Error Rate", fontsize=12)
    ax.legend(frameon=False, fontsize=10)
    ax.grid(alpha=0.3, ls="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(bottom=1)

    # Right: p99 FCT slowdown
    ax2 = axes[1]
    ax2.plot(logx(cw_rates), [cw_results[r]["all_p99"] for r in cw_rates],
             "D-", color=CW_COLOR, lw=2, ms=7, label="ConWeave")
    if ecmp_rates:
        ax2.plot(logx(ecmp_rates), [ecmp_results[r]["all_p99"] for r in ecmp_rates],
                 "o--", color=ECMP_COLOR, lw=2, ms=7, label="ECMP")
    ax2.set_xscale("log")
    ax2.set_xlabel("Per-Link Packet Error Rate", fontsize=12)
    ax2.set_ylabel("p99 FCT Slowdown", fontsize=12)
    ax2.set_title("p99 FCT Slowdown vs Error Rate", fontsize=12)
    ax2.legend(frameon=False, fontsize=10)
    ax2.grid(alpha=0.3, ls="--")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.set_ylim(bottom=1)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        out = os.path.join(args.output_dir, f"greyfailure_sensitivity.{ext}")
        fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"\n  saved greyfailure_sensitivity.png / .pdf")
    plt.close()

    # Large-flow breakdown
    fig2, axes2 = plt.subplots(1, 2, figsize=(12, 4.5))
    ax3 = axes2[0]
    if any("large_avg" in cw_results[r] for r in cw_rates):
        ax3.plot(logx(cw_rates), [cw_results[r].get("large_avg", np.nan) for r in cw_rates],
                 "D-", color=CW_COLOR, lw=2, ms=7, label="ConWeave large avg")
    if ecmp_rates and any("large_avg" in ecmp_results[r] for r in ecmp_rates):
        ax3.plot(logx(ecmp_rates), [ecmp_results[r].get("large_avg", np.nan) for r in ecmp_rates],
                 "o--", color=ECMP_COLOR, lw=2, ms=7, label="ECMP large avg")
    ax3.set_xscale("log")
    ax3.set_xlabel("Per-Link Packet Error Rate", fontsize=12)
    ax3.set_ylabel("Large-Flow Avg FCT Slowdown", fontsize=12)
    ax3.set_title("Large flows: avg slowdown vs error rate", fontsize=12)
    ax3.legend(frameon=False, fontsize=10)
    ax3.grid(alpha=0.3, ls="--")
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)
    ax3.set_ylim(bottom=1)

    ax4 = axes2[1]
    if any("large_p99" in cw_results[r] for r in cw_rates):
        ax4.plot(logx(cw_rates), [cw_results[r].get("large_p99", np.nan) for r in cw_rates],
                 "D-", color=CW_COLOR, lw=2, ms=7, label="ConWeave large p99")
    if ecmp_rates and any("large_p99" in ecmp_results[r] for r in ecmp_rates):
        ax4.plot(logx(ecmp_rates), [ecmp_results[r].get("large_p99", np.nan) for r in ecmp_rates],
                 "o--", color=ECMP_COLOR, lw=2, ms=7, label="ECMP large p99")
    ax4.set_xscale("log")
    ax4.set_xlabel("Per-Link Packet Error Rate", fontsize=12)
    ax4.set_ylabel("Large-Flow p99 FCT Slowdown", fontsize=12)
    ax4.set_title("Large flows: p99 slowdown vs error rate", fontsize=12)
    ax4.legend(frameon=False, fontsize=10)
    ax4.grid(alpha=0.3, ls="--")
    ax4.spines["top"].set_visible(False)
    ax4.spines["right"].set_visible(False)
    ax4.set_ylim(bottom=1)

    fig2.tight_layout()
    for ext in ("png", "pdf"):
        out = os.path.join(args.output_dir, f"greyfailure_large_flows.{ext}")
        fig2.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  saved greyfailure_large_flows.png / .pdf")
    plt.close()

    # Summary table
    print("\n" + "=" * 80)
    print(f"{'Scheme':<10}{'ErrorRate':>12}{'AllAvg':>9}{'Allp99':>9}"
          f"{'LargeAvg':>10}{'LargeP99':>10}{'N':>8}")
    print("-" * 80)
    for lb_name, d in (("ConWeave", cw_results), ("ECMP", ecmp_results)):
        for r in sorted(d):
            s = d[r]
            print(f"{lb_name:<10}{r:>12.1e}{s['all_avg']:>9.3f}{s['all_p99']:>9.3f}"
                  f"{s.get('large_avg', float('nan')):>10.3f}"
                  f"{s.get('large_p99', float('nan')):>10.3f}{s['n_total']:>8}")


if __name__ == "__main__":
    main()
