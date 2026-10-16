#!/bin/bash
set -euo pipefail

if [[ ! -f Qleverfile ]]; then
  printf '%s\n' "Missing /data/Qleverfile. Run the documented setup and indexing steps first." >&2
  exit 1
fi

# Read only the simple index name and text-index setting. The CLI remains
# responsible for the full Qleverfile (including its download commands).
mapfile -t config < <(python3 - <<'PY'
from configparser import ConfigParser

config = ConfigParser(interpolation=None)
config.read("Qleverfile")
name = config.get("data", "NAME")
if not name or "/" in name or name.startswith("-") or "${" in name:
    raise ValueError("Use a literal dataset NAME without slashes in Qleverfile")
print(name)
text_index = config.get("index", "TEXT_INDEX", fallback="none").strip()
print("no" if text_index == "none" else "yes")
PY
)
if [[ ${#config[@]} -ne 2 ]]; then
  printf '%s\n' "Could not read dataset configuration." >&2
  exit 1
fi

args=(
  -i "${config[0]}" -p 7001
  -m "$QLEVER_MEMORY_FOR_QUERIES"
  -c "$QLEVER_CACHE_MAX_SIZE"
  -e "$QLEVER_CACHE_SINGLE_ENTRY"
  -j "$QLEVER_CONCURRENT_QUERIES"
  -s "$QLEVER_QUERY_TIMEOUT"
  --service-allowed-iri-prefixes "$QLEVER_SERVICE_ALLOW_PREFIX"
)
if [[ "${config[1]}" == yes ]]; then
  args+=(-t)
fi
# Do not inherit the sample Qleverfile's predictable ACCESS_TOKEN. With no
# token, privileged operations (including updates) are disabled.
exec qlever-server "${args[@]}"
