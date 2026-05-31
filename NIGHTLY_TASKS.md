# Nightly / unattended work queue

This file is the contract for letting Claude Code work while you sleep. You fill
the **Queue**; Claude works it top-to-bottom and appends to the **Run log**.
Most prompts are pre-approved by `.claude/settings.json`; the `.claude/hooks/guard.sh`
hook is the hard backstop that blocks catastrophic commands even in bypass mode.

---

## Rules of engagement (always in force)

**Claude MAY, unattended:**
- Read / edit / write files in this repo
- Run `python3`, `pytest`, byte-compile, headless Streamlit dry-runs
- `git add` + `git commit` locally (small, well-described commits)
- Regenerate derived data (parquet/CSV outputs) from existing local sources

**Claude must NEVER, unattended (these need you, awake):**
- `git push` — leave commits local; you review + push in the morning
  *(unless a queue item explicitly says "push when green")*
- Acquire API keys, sign up for services, or `pip/npm/brew install` new deps
- Send email, store payment cards, or initiate payments
- Touch FICA / IRS / F-1 / payroll-tax / visa language on any public-facing
  surface (outreach copy is screened by `_assert_public_safe`)
- `rm -rf`, force-push, `git reset --hard`, `sudo` — blocked by guard.sh

**Working style:** one queue item = one focused commit. If an item is ambiguous
or its premise turns out wrong, STOP, write the question into the Run log, and
move to the next item — don't guess on irreversible things.

---

## How to launch an overnight run

The Claude Code **CLI** must be on your PATH. Find it in your normal terminal:

```bash
which claude        # e.g. /opt/homebrew/bin/claude or ~/.claude/local/claude
```

If nothing prints, install the CLI first (one-time, your call):
`npm install -g @anthropic-ai/claude-code`.

**Option A — one-shot before bed (simplest):**
```bash
cd /Users/dantetolbedantert/florence-work/labor-economics-agent
claude -p "Work NIGHTLY_TASKS.md top to bottom. Follow its rules of engagement. Commit each item locally; do not push." \
  --permission-mode acceptEdits
```
(`acceptEdits` + the allow-list in `.claude/settings.json` covers the routine
work and still respects deny rules + the guard hook. Use
`--dangerously-skip-permissions` only if you want zero prompts — the guard hook
still blocks the catastrophic stuff.)

**Option B — scheduled nightly via launchd (macOS):**
Create `~/Library/LaunchAgents/dev.florence.nightly.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.florence.nightly</string>
  <key>ProgramArguments</key><array>
    <string>/ABSOLUTE/PATH/TO/claude</string>   <!-- from `which claude` -->
    <string>-p</string>
    <string>Work NIGHTLY_TASKS.md top to bottom per its rules. Commit locally; do not push.</string>
    <string>--permission-mode</string><string>acceptEdits</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/dantetolbedantert/florence-work/labor-economics-agent</string>
  <key>StandardOutPath</key><string>/tmp/florence_nightly.log</string>
  <key>StandardErrorPath</key><string>/tmp/florence_nightly.err</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer>
  </dict>
</dict></plist>
```
Then: `launchctl load ~/Library/LaunchAgents/dev.florence.nightly.plist`
(unload with `launchctl unload …` to stop it).

> Note: Claude Code has **no built-in scheduler** — launchd/cron is the trigger.
> Anthropic does not recommend `--dangerously-skip-permissions` for production;
> the deny-list + guard hook are the defense-in-depth that make an unattended
> run safer, not safe-by-default. Keep queue items concrete and reversible.

---

## Queue  (you fill this — Claude works top to bottom)

- [ ] _example: "Add a CSV export button to the employer pipeline table."_
- [ ]
- [ ]

---

## Run log  (Claude appends; newest at top)

<!-- YYYY-MM-DD HH:MM — item — outcome — commit sha / question -->
