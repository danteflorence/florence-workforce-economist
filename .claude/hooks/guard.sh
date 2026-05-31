#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Florence safety guard — PreToolUse hook (matcher = Bash)
# ─────────────────────────────────────────────────────────────────────────
# Hooks fire even under --dangerously-skip-permissions / bypassPermissions,
# so this is the LAST line of defense for unattended/overnight runs. It hard-
# blocks catastrophic commands regardless of any allow rule.
#
#   exit 2  => BLOCK the tool call; stderr is fed back to Claude as the reason
#   exit 0  => allow (the normal permission system still applies)
#
# Intentionally NOT using `set -e`: each `grep && deny` returns non-zero when
# the pattern does NOT match, which under `set -e` would abort the script
# early and skip later checks. Plain control flow is correct here.
# ─────────────────────────────────────────────────────────────────────────

payload="$(cat)"
cmd="$(printf '%s' "$payload" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null)"

deny() {
  echo "BLOCKED by Florence safety guard: $1. This is denied for unattended/overnight safety. If you genuinely need it, run it yourself in an interactive session." >&2
  exit 2
}

# Empty / unparseable command → let the permission system decide.
[ -z "$cmd" ] && exit 0

# ── Catastrophic file removal ──
printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])rm[[:space:]]+-[[:alnum:]]*[rf]' && deny "rm with -r/-f flags"
printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])rm[[:space:]]+(-[[:alnum:]]*[[:space:]]+)*(/|~|\$HOME)([[:space:]/]|$)' && deny "rm targeting / or home"

# ── Git history / remote destruction ──
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push[[:space:]]+(.*[[:space:]])?(--force-with-lease|--force|-f)([[:space:]=]|$)' && deny "git force-push"
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+reset[[:space:]]+--hard' && deny "git reset --hard"
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+clean[[:space:]]+-[[:alnum:]]*f' && deny "git clean -f"
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+checkout[[:space:]]+--[[:space:]]' && deny "git checkout -- (discards working changes)"
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+branch[[:space:]]+-D' && deny "git branch -D (force delete)"

# ── Privilege escalation / disk / fork bomb ──
printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])sudo([[:space:]]|$)' && deny "sudo"
printf '%s' "$cmd" | grep -Eq 'mkfs|dd[[:space:]]+if=.*of=/dev/|>[[:space:]]*/dev/(sd|disk|nvme)' && deny "raw disk write"
printf '%s' "$cmd" | grep -Eq ':\(\)[[:space:]]*\{[[:space:]]*:' && deny "fork bomb"

# ── Secret exfiltration (best-effort): network tool touching a secret file ──
printf '%s' "$cmd" | grep -Eq '(curl|wget|nc|scp).*(\.env|\.auth_secret|auth_users|auth_sessions|auth_otp|secrets\.toml|id_rsa|\.pem)' && deny "possible secret exfiltration"

exit 0
