#!/usr/bin/env python3
"""Opt-in external timer entrypoint; needs PYTHONPATH=src on a trusted host."""
from ai_product_factory.independent_scheduler_watchdog import main

if __name__ == "__main__":
    raise SystemExit(main())
