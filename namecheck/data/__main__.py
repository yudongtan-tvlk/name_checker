"""CLI: python3 -m namecheck.data  [--config path]

Builds the per-country cache for the countries/sources enabled in config.yaml.
"""
import sys

from namecheck.data.config import load_config
from namecheck.data.manager import DataManager


def main(argv):
    path = None
    if "--config" in argv:
        path = argv[argv.index("--config") + 1]
    config = load_config(path) if path else load_config()
    DataManager(config).run()


if __name__ == "__main__":
    main(sys.argv[1:])
