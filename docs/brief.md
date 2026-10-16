# AI Account Switcher Brief
Status: Approved 2026-10-16

## Problem (2 to 3 sentences)
I use two Claude Pro subscriptions on one Mac (personal and work). When one hits its usage limit mid-task, switching accounts means logging out and back in, and the agent loses its session, memory and context, so I have to re-explain everything. There is no reliable way to keep one continuous working session across accounts, or across other AI tools later.

## Target user and main job-to-be-done
- **User:** me, a solo developer on one Mac with two Claude Pro accounts (personal and work), using Claude Code in the terminal for long agent tasks.
- **Main job:** when one account hits its usage limit, switch to the other account in seconds and pick up the same Claude Code session, with its memory, project context and conversation history intact, so the agent keeps going without me re-explaining anything.

## Pitch (3 sentences max)
AI Account Switcher keeps two Claude Code accounts signed in side by side on one Mac, both reading and writing the same sessions, memory and project context. When one account hits its limit, one command resumes the exact same session on the other account. Its provider plug-in shape leaves room to add other AI tools later.

## Success metrics (measurable)
- **Switch speed:** in the first 2 weeks of daily use, 95% of switches after a usage limit resume the same Claude Code session on the other account in under 30 seconds, with one command.
- **Zero context loss:** in the same 2 weeks, 0 switches where I have to re-explain the task, measured by the resumed session showing the prior conversation and memory.

## MVP scope (3 to 5 bullets)
1. **Two accounts, both signed in:** personal and work Claude Code (CLI) logins live side by side on one Mac, each with its own Keychain credential, and `ais desktop <account>` opens each account's own Claude Desktop window side by side.
2. **One shared brain:** both accounts use the same `~/.claude` (session transcripts, memory, CLAUDE.md, skills, subagents, settings), so either one sees everything.
3. **One-command switch and resume:** a command such as `ais switch work` reopens the current session (same session ID) under the other account.
4. **Status at a glance:** `ais status` shows which account is active and whether each one is signed in, and an optional SwiftBar menu bar plugin shows the same with one-click switch actions.
5. **Built for more AIs later:** a small provider plug-in shape with only Claude implemented, plus a reversible install that backs up `~/.claude` first.

## Non-goals (at least 5)
1. No claude.ai web chat. Claude Desktop only as one separate instance per account; no single Desktop that lists both accounts' sessions (next release, rojcarranza/ai-account-switcher#1).
2. No automatic switching when a limit hits; the user runs the switch command.
3. No second AI provider implemented; only the plug-in shape exists.
4. No native menu bar or GUI app; an optional SwiftBar plugin shows status and switch actions.
5. No sync across machines; one Mac, local files only.
6. No storing, reading or copying of passwords or tokens; logins stay in macOS Keychain and the official `claude` login flow.
7. No usage or limit tracking or forecasting.
8. No more than 2 accounts tested in the MVP; the design must not block a third.

## Constraints (budget, cloud, compliance, timeline)
- **Budget:** $0 beyond the two existing Claude Pro subscriptions. No paid services, no servers.
- **Platform:** macOS, zsh, Claude Code CLI installed natively. The `claude` login on macOS lives in Keychain.
- **Cloud:** none. Everything runs and stays local.
- **Compliance:** use stays within Anthropic's Consumer Terms and Usage Policy for both accounts (see open question 1).
- **Work account:** if the work account is tied to an employer, that employer's policies on mixing personal and work data apply, since shared memory means both accounts see everything.
- **Safety:** never edit Keychain secrets directly; back up `~/.claude` before any change; every install step can be undone.
- **Tooling:** Superpowers 7.0.0 was installed but could not be live-loaded in the remote planning session, so its skills were followed from disk.
- **Timeline:** MVP usable within 2 weeks of part-time work.

## Open questions
1. **Terms of service:** do Anthropic's Consumer Terms allow one person to use two Pro accounts and switch between them when a limit hits? Verify against the current terms before building.
2. **Session handoff:** does `claude --resume <id>` under the second account reliably continue a session the first account started, using the shared `~/.claude`? Prove with a spike on the Mac in phase 4.
3. **Global config file:** `~/.claude.json` (signed-in account info) sits outside `~/.claude`. Does it need a per-account split, or is the Keychain split (`CLAUDE_SECURESTORAGE_CONFIG_DIR`) enough?
4. **Running at the same time:** is it safe for both accounts to run Claude Code at once against the same `~/.claude` (file locking, transcript corruption)?
5. **Next provider:** which AI comes after Claude (Codex CLI, Gemini CLI, ...)? This decides the plug-in shape's details.
6. **Unread sources:** the swalahamani.com post and the Google Drive file could not be read from the planning session; the user to paste or summarize them.

## References
- kevinchau/claude-switcher (shared `~/.claude`, per-account Keychain slot): https://github.com/kevinchau/claude-switcher
- MelkonTech/two-claude-accounts-mac (separate `CLAUDE_CONFIG_DIR`, desktop app cloning): https://github.com/MelkonTech/two-claude-accounts-mac
- https://melkon.tech/blog/two-claude-accounts-mac
- https://frontendhire.com/learn/ai/courses/using-multiple-claude-accounts/overview

## Change log
- 2026-10-16: MVP bullet 4 and non-goal 4 changed to add an optional SwiftBar menu bar plugin (user approved; Claude Switcher-style menu status without a native app).
- 2026-10-16: MVP bullet 1 and non-goal 1 changed to add one Claude Desktop instance per account (user approved; ais replaces Claude Switcher, which the user will uninstall; design `docs/superpowers/specs/2026-10-16-ais-desktop-design.md`).
