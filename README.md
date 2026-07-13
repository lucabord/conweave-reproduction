# ConWeave Reproduction — How to Run

Reproduction of the NS-3 evaluation of *"Network Load Balancing with
In-network Reordering Support for RDMA"* (Song et al., ACM SIGCOMM 2023,
https://doi.org/10.1145/3603269.3604849).

The full report is in [`report.md`](report.md) (rendered as `report.pdf`).
This page explains how to re-run everything from scratch.

## Requirements

- Docker (on Apple Silicon: Docker Desktop with Rosetta 2 — every build/run
  must be pinned to `--platform linux/amd64`).
- ~16 GB of memory allocated to Docker.
- Python 3 with `numpy` and `matplotlib` on the host (for the analysis
  scripts, which can also be run inside the container).

## 1. Get the code

The ConWeave artifact is not standalone: it replaces the `ns-3.19` directory
inside the official `ns-allinone-3.19` bundle.

```bash
git clone https://github.com/conweave-project/conweave-ns3
wget https://www.nsnam.org/releases/ns-allinone-3.19.tar.bz2
tar -xf ns-allinone-3.19.tar.bz2
rm -rf ns-allinone-3.19/ns-3.19
cp -r conweave-ns3 ns-allinone-3.19/ns-3.19
```

## 2. Build the Docker image and NS-3

Place the artifact's `Dockerfile` in `ns-allinone-3.19/`, then:

```bash
cd ns-allinone-3.19
docker build --platform linux/amd64 -t cw-sim:sigcomm23ae .
docker run --platform linux/amd64 -v $(pwd):/root cw-sim:sigcomm23ae \
    bash -c "cd ns-3.19; ./waf configure --build-profile=optimized; ./waf"
```

## 3. Run the simulations

The artifact's `autorun.sh` launches the 8 experiments of one load level
(4 load balancers × 2 flow controls). Edit `RUNTIME` (default `0.1` seconds
of traffic generation) and `NETLOAD` (`50` or `80`) at the top of the script,
then:

```bash
docker run --platform linux/amd64 -v $(pwd):/root cw-sim:sigcomm23ae \
    bash -c "cd ns-3.19; ./autorun.sh"
```

Run it once with `NETLOAD="50"` and once with `NETLOAD="80"` to cover both
load levels used in the report. Each run writes its raw output under
`ns-3.19/mix/output/<run-id>/` and registers itself in `ns-3.19/mix/.history`.

Note: `autorun.sh` starts all 8 simulations simultaneously (~1 CPU core and
~1.1 GB of memory each). On a memory-constrained machine, launch the
individual `run.py` commands in smaller batches instead.

## 4. Generate the figures

All plotting scripts are post-processing only: they read the raw runs from
`ns-3.19/mix/output/<run-id>/` and the `.history` file written in step 3, so
**the corresponding simulations must have been run first**.

**Reproduction figures (report S4).** The FCT-slowdown plots (paper
Figures 12-13) come from the artifact's analysis script; the
uplink-imbalance CDF (paper Figure 14) comes from our own script, which
reimplements the artifact's `plot_uplink.py` algorithm and automatically
selects the baseline runs:

```bash
cd ns-3.19/analysis
python3 plot_fct.py                          # FCT slowdown vs flow size

cd <this-repo>/scripts
python3 reproduce_fig14.py \
    --data_dir <ns-3.19>/mix/output \
    --history  <ns-3.19>/mix/.history \
    --output_dir ../figures                  # uplink-imbalance CDF
```

**Further-exploration figures (report S5).** The buffer-size and
grey-failure sweeps are ordinary artifact runs with `BUFFER_SIZE` /
`ERROR_RATE_PER_LINK` varied in the run configuration; once those runs
exist, our scripts produce the S5 figures and tables:

```bash
cd <this-repo>/scripts
python3 plot_buffer_sensitivity.py \
    --data_dir <ns-3.19>/mix/output \
    --history  <ns-3.19>/mix/.history_buffer_full \
    --output_dir ../figures                  # report Figures 11-12, Table 2

python3 plot_greyfailure_sensitivity.py \
    --data_dir <ns-3.19>/mix/output \
    --history  <ns-3.19>/mix/.history_greyfailure \
    --output_dir ../figures                  # report Figures 13-14, Table 3
```

Each script's docstring documents the exact input format it expects. The
figures used by the report are stored in `figures/`.

## 5. Build the report PDF

Requires `md2pdf` (`python3 -m pip install "md2pdf[cli]"`):

```bash
make        # renders report.md -> report.pdf
```
