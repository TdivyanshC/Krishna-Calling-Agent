# -*- coding: utf-8 -*-
"""run.py — ingest + enrich + checks in one shot. Usage: python3 run.py [--since-days 30]"""
import argparse

import checks
import enrich
import ingest

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=30)
    args = ap.parse_args()

    ingest.run()
    enrich.run(args.since_days)
    run_id = checks.run()
    print(f"\nDashboard: python3 dashboard.py, then open http://127.0.0.1:8787/runs/{run_id}")
