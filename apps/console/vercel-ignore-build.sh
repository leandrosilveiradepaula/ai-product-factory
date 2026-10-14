#!/bin/sh
# Called by Vercel with apps/console as the project Root Directory.
# Vercel: exit 0 = ignore this deployment; exit 1 = build.
set -u

case "${VERCEL_GIT_COMMIT_REF-}" in
  preview/pr-*)
    number="${VERCEL_GIT_COMMIT_REF#preview/pr-}"
    case "$number" in
      ''|*[!0-9]*) exit 0 ;;
    esac

    previous="${VERCEL_GIT_PREVIOUS_SHA-}"
    # Compare all changes since the last successful deployment, not only HEAD^.
    # A shallow clone or unknown previous SHA cannot prove equivalence: build.
    if printf '%s' "$previous" | grep -Eq '^[0-9a-f]{40}$' \
      && git cat-file -e "${previous}^{commit}" 2>/dev/null; then
      git diff --quiet "$previous" HEAD -- .
      case "$?" in
        0) exit 0 ;;
        *) exit 1 ;;
      esac
    fi
    exit 1
    ;;
  preview/*) exit 0 ;;
  main)
    # Unchanged production policy: only Console or release policy edits build.
    git diff --quiet HEAD^ HEAD -- . ../../config/factory.release-policy.v1.json
    case "$?" in
      0) exit 0 ;;
      *) exit 1 ;;
    esac
    ;;
  '')
    # Build rather than silently suppress a deployment if system env is missing.
    exit 1
    ;;
  *) exit 0 ;;
esac
