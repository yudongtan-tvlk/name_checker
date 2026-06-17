"""namecheck data pipeline: config-driven, per-country cache builder.

Public entry points:
    from namecheck.data.config import load_config, COUNTRY_CC, cache_file, ...
    python3 -m namecheck.data            # build the cache for enabled countries
"""
from namecheck.data.config import load_config, Config  # noqa: F401
