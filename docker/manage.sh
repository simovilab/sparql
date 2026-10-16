#!/bin/bash
set -euo pipefail

case "${1:-help}" in
  setup-imdb)
    if [[ -e Qleverfile ]]; then
      printf '%s\n' "Qleverfile already exists; refusing to replace it." >&2
      exit 1
    fi
    exec qlever setup-config imdb
    ;;
  get-data)
    exec qlever get-data
    ;;
  index)
    shift
    exec qlever index --system native "$@"
    ;;
  *)
    printf '%s\n' \
      "Usage: docker compose run --rm qlever-manage setup-imdb|get-data|index" \
      "Stop the engine before rebuilding an existing index." >&2
    exit 1
    ;;
esac
