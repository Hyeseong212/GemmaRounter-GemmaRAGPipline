#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/rb/AI/gemma-rag"
KNOWN_ACTIONS="start restart stop status ready logs test sample trace stream"
ACTION="start"

if [[ $# -gt 0 ]]; then
  case " ${KNOWN_ACTIONS} " in
    *" $1 "*)
      ACTION="$1"
      shift || true
      ;;
  esac
fi

exec "${PROJECT_DIR}/scripts/manage_local_gemma.sh" "${ACTION}" "$@"
