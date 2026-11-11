#!/usr/bin/env bash
# CYBER WORKSPACE — one-command GitHub publish (see Documentation/GITHUB_PUSH.md).
#
#   GITHUB_TOKEN=ghp_xxxx bash Build/Scripts/push_to_github.sh <github-username> [repo-name]
#
# 1. creates the repo via the GitHub API (HTTP 422 "already exists" is accepted)
# 2. adds a CLEAN remote (no token persisted in .git/config)
# 3. pushes main -> both CI workflows start automatically
#
# The token is read from the environment only and is never written to disk.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: GITHUB_TOKEN=<token> $0 <github-username> [repo-name]"
    exit 2
fi
if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "error: GITHUB_TOKEN environment variable is required (never hardcode it)"
    exit 2
fi

GH_USER="$1"
REPO="${2:-cyber-workspace}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"   # repository root (Cyber Workspace/)
cd "$ROOT"

echo "== CYBER WORKSPACE publish: ${GH_USER}/${REPO} =="

status="$(curl -s -o /dev/null -w '%{http_code}' -X POST https://api.github.com/user/repos \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -d "{\"name\":\"${REPO}\",\"private\":false,\"has_issues\":true,\
\"description\":\"CYBER WORKSPACE - isolated multi-task workspace (Windows host + Android companion)\"}")"

case "$status" in
    201) echo "repo created: https://github.com/${GH_USER}/${REPO}" ;;
    422) echo "repo already exists - continuing" ;;
    401) echo "error: token rejected (401) - check GITHUB_TOKEN"; exit 1 ;;
    *)   echo "error: repo create failed (HTTP ${status})"; exit 1 ;;
esac

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${GH_USER}/${REPO}.git"

# token passed inline for this single push only; remote URL stays clean
git push "https://x-access-token:${GITHUB_TOKEN}@github.com/${GH_USER}/${REPO}.git" main
echo "pushed. CI: https://github.com/${GH_USER}/${REPO}/actions"
echo "next: download artifacts and place them into Installer/Windows and Installer/Android (GITHUB_PUSH.md section 4)"
