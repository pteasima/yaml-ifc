#!/usr/bin/env bash
# Push rendered plan images to the previews branch and keep one PR comment.
# Private-repo members see the image via the blob ?raw=true URL (cookies).
# raw.githubusercontent.com does not serve private files.
set -euo pipefail

: "${GH_TOKEN:?}"
: "${PR:?}"
: "${SHA:?}"
: "${REPO:?}"
: "${RUN_ID:?}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PREVIEW_BRANCH=previews
DEST="pr-${PR}/${SHA}"
MARKER="<!-- yaml-ifc-plan-preview -->"
RUN_URL="https://github.com/${REPO}/actions/runs/${RUN_ID}"

shopt -s nullglob
pngs=(dist/*.png)
shopt -u nullglob
if ((${#pngs[@]} == 0)); then
  echo "no PNGs in dist/" >&2
  exit 1
fi

push_ok=0
workdir="$(mktemp -d)"
if git fetch origin "${PREVIEW_BRANCH}" >/dev/null 2>&1; then
  git worktree add --detach "$workdir" "origin/${PREVIEW_BRANCH}"
  git -C "$workdir" checkout -B "${PREVIEW_BRANCH}"
else
  git worktree add --detach "$workdir" HEAD
  git -C "$workdir" checkout --orphan "${PREVIEW_BRANCH}"
  git -C "$workdir" rm -rf . >/dev/null 2>&1 || true
fi

cleanup() {
  git worktree remove --force "$workdir" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "${workdir}/${DEST}"
for png in "${pngs[@]}"; do
  cp "$png" "${workdir}/${DEST}/"
done
if [[ ! -f "${workdir}/README.md" ]]; then
  printf '%s\n' "Generated plan previews for pull-request comments. One directory per PR and commit." > "${workdir}/README.md"
fi

git -C "$workdir" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git -C "$workdir" config user.name "github-actions[bot]"
git -C "$workdir" add README.md "${DEST}"
if git -C "$workdir" diff --cached --quiet; then
  echo "preview already published"
  push_ok=1
else
  git -C "$workdir" commit -m "Plan preview for PR #${PR} @ ${SHA:0:7}"
  if git -C "$workdir" push "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" "HEAD:${PREVIEW_BRANCH}"; then
    push_ok=1
  else
    echo "push to ${PREVIEW_BRANCH} failed; the comment will link the artifact" >&2
  fi
fi

{
  echo "${MARKER}"
  echo "### Plan preview"
  echo
  echo "Rendered from \`${SHA}\`."
  echo
  if ((push_ok)); then
    for png in "${pngs[@]}"; do
      name="$(basename "$png")"
      url="https://github.com/${REPO}/blob/${PREVIEW_BRANCH}/${DEST}/${name}?raw=true"
      echo "![${name}](${url})"
      echo
    done
  else
    echo "The preview image could not be pushed to \`${PREVIEW_BRANCH}\`. Download **plan-previews** from the workflow run."
    echo
  fi
  echo "[Workflow run](${RUN_URL}) (artifact \`plan-previews\`)."
} > /tmp/plan-comment.md

existing="$(gh api --paginate "repos/${REPO}/issues/${PR}/comments" \
  --jq ".[] | select(.body | contains(\"${MARKER}\")) | .id" | head -n 1 || true)"
if [[ -n "${existing}" ]]; then
  gh api -X PATCH "repos/${REPO}/issues/comments/${existing}" --raw-field body="$(cat /tmp/plan-comment.md)" >/dev/null
  echo "updated comment ${existing}"
else
  gh api -X POST "repos/${REPO}/issues/${PR}/comments" --raw-field body="$(cat /tmp/plan-comment.md)" >/dev/null
  echo "posted comment"
fi
