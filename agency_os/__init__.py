"""Agency OS — Turnkey autonomous AI organization platform."""

# Register vendor/swarm on sys.path so SWARM modules are importable
# everywhere agency_os is used.  Must happen before any `from swarm …` import.
import agency_os._vendor_path as _vendor_path  # noqa: F401
