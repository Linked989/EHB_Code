# C² Ledger — Python-only Mocked Contracts

This version keeps **everything in Python**. The "contracts" directory contains a Python mock
that represents the theoretical on-chain contract. In practice, it delegates to the in-process
ledger and validator so you can demo, measure, and visualize without blockchain dependencies.

## Quick start
```
python -m venv .venv
source .venv/bin/activate
pip install flask
python sims/run_demo.py
python visualizer/server.py
```
