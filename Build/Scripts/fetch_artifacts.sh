#!/usr/bin/env bash
# CYBER WORKSPACE — fetch real CI artifacts, place them, repack the backup.
#
#   GITHUB_TOKEN=ghp_xxxx bash Build/Scripts/fetch_artifacts.sh <github-username> [repo-name]
#
# What it does (Documentation/GITHUB_PUSH.md §4–§5):
#   1. finds the latest successful run of windows-build and android-build on main
#      (or the run ids given after --run)
#   2. downloads the artifacts:
#        CyberWorkspace-installer          -> Installer/Windows/
#        CyberWorkspace-portable           -> Installer/Windows/portable/
#        CyberWorkspace-remote-debug-apk   -> Installer/Android/cyber-workspace-remote-debug.apk
#   3. rebuilds Backup/Cyber-Workspace-Full-Backup.zip (with the artefacts in,
#      secret-class files excluded) and prints file count + SHA-256
#
#   bash Build/Scripts/fetch_artifacts.sh --backup-only
#   rebuilds the backup zip alone (no network, no token).
#
# The token is read from the environment only and is never written to disk.
set -euo pipefail

GH_USER="${1:-}"
REPO="${2:-cyber-workspace}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"   # repository root (Cyber Workspace/)
cd "$ROOT"

API="https://api.github.com/repos"
auth_header() { printf 'Authorization: Bearer %s' "${GITHUB_TOKEN:?error: GITHUB_TOKEN environment variable is required}"; }

repack_backup() {
    echo "== repacking Backup/Cyber-Workspace-Full-Backup.zip =="
    python3 - "$ROOT" <<'PY'
import hashlib, sys, zipfile
from pathlib import Path

root = Path(sys.argv[1])
out = root / "Backup" / "Cyber-Workspace-Full-Backup.zip"
skip_dirs = {".git", "__pycache__", ".pytest_cache", ".venv", ".gradle",
             "build", "dist", ".idea", ".vs"}
skip_suffixes = {".pyc", ".pyo", ".pyd"}

def skip(p: Path) -> bool:
    if p == out or not p.is_file():
        return True
    if any(s in p.parts for s in skip_dirs):
        return True
    if p.suffix in skip_suffixes:
        return True
    if p.name.endswith((".pem", ".key", ".keystore", ".lock")):
        return True
    if p.name in {"settings.json"} or p.name.startswith("workspace.db"):
        return True
    return False

files = sorted(p for p in root.rglob("*") if not skip(p))
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files:
        z.write(p, p.relative_to(root).as_posix())
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None, "corrupt zip member"
    n = len(z.namelist())
assert n == len(files), "member count mismatch"
sha = hashlib.sha256(out.read_bytes()).hexdigest()
print(f"backup : {out.name}  files={n}  size={out.stat().st_size/1024:.0f} KiB")
print(f"sha256 : {sha}")
PY
}

if [ "${1:-}" = "--backup-only" ]; then
    repack_backup
    exit 0
fi

if [ -z "$GH_USER" ]; then
    echo "usage: GITHUB_TOKEN=<token> $0 <github-username> [repo-name]" >&2
    echo "       $0 --backup-only" >&2
    exit 2
fi

command -v curl >/dev/null || { echo "error: curl is required"; exit 1; }
command -v unzip >/dev/null || { echo "error: unzip is required"; exit 1; }

fetch_artifact() {  # $1=workflow-file  $2=artifact-name  $3=dest-dir
    local wf="$1" art="$2" dest="$3" run_id art_id url tmp
    echo "== $wf :: $art =="
    run_id="$(curl -sSfL -H "$(auth_header)" \
        "$API/$GH_USER/$REPO/actions/workflows/$wf/runs?branch=main&status=success&per_page=1" \
        | python3 -c 'import json,sys; r=json.load(sys.stdin)["workflow_runs"]; print(r[0]["id"] if r else "")')"
    [ -n "$run_id" ] || { echo "error: no successful run of $wf on main — push first and wait for Actions to finish"; exit 1; }
    echo "   run: https://github.com/$GH_USER/$REPO/actions/runs/$run_id"
    art_id="$(ART="$art" curl -sSfL -H "$(auth_header)" \
        "$API/$GH_USER/$REPO/actions/runs/$run_id/artifacts?per_page=100" \
        | python3 -c 'import json,sys,os
arts=json.load(sys.stdin)["artifacts"]
name=os.environ["ART"]
m=[a for a in arts if a["name"]==name and not a["expired"]]
print(m[0]["id"] if m else "")')"
    [ -n "$art_id" ] || { echo "error: artifact '$art' not found in run $run_id"; exit 1; }
    tmp="$(mktemp -d)"
    curl -sSfL -H "$(auth_header)" \
        "$API/$GH_USER/$REPO/actions/artifacts/$art_id/zip" -o "$tmp/artifact.zip"
    unzip -qo "$tmp/artifact.zip" -d "$tmp/x"
    mkdir -p "$dest"
    case "$art" in
        CyberWorkspace-installer)
            mv "$tmp"/x/*-setup.exe "$dest/" ;;
        CyberWorkspace-portable)
            rm -rf "$dest"; mkdir -p "$dest"
            mv "$tmp"/x/CyberWorkspace "$dest/" ;;
        CyberWorkspace-remote-debug-apk)
            mv "$tmp"/x/app-debug.apk "$dest/cyber-workspace-remote-debug.apk" ;;
    esac
    rm -rf "$tmp"
    echo "   placed -> $dest"
}

fetch_artifact windows-build.yml CyberWorkspace-installer "Installer/Windows"
fetch_artifact windows-build.yml CyberWorkspace-portable  "Installer/Windows/portable"
fetch_artifact android-build.yml CyberWorkspace-remote-debug-apk "Installer/Android"

echo
repack_backup
echo
echo "done. verify: Installer/Windows + Installer/Android now contain the real builds."
