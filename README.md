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

The artifact's analysis scripts read the raw per-flow FCT files and produce
the plots used in the report:

```bash
cd ns-3.19/analysis
python3 plot_fct.py      # FCT slowdown vs flow size (paper Figures 12-13)
python3 plot_uplink.py   # uplink throughput-imbalance CDF (paper Figure 14)
```

The figures used by the report are stored in `figures/`.

## 5. Build the report PDF

Requires `md2pdf` (`python3 -m pip install "md2pdf[cli]"`):

```bash
make        # renders report.md -> report.pdf
```
