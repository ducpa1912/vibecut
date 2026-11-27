# Workflow setup review · 2026-11-27

Revision: Claude and Codex share the original integration checkout. OpenCode uses code-only worktrees. The shared-index rehearsal below is historical. Consolidation retained the old scratch data and reduced the legacy Codex worktree from 5.5 GiB to 16 MiB.

**Workflow ready. Feature dispatch gated for both lanes.** The local OpenCode catalog advertised openai/gpt-6.2-astra, openai/gpt-6.2-sol and xingchi/gpt-6.1-sol. A read-only service probe with the explicit directory header resolved to this DuckSuite checkout. Omitting the header resolved to the user's home directory.

Local OpenCode skill discovery found Impeccable, Grill Me, Loop Me and Code Review. The Pstack installation under `~/.local/share/pstack/skills` contains `swarm`, `thermo-nuclear-review` and `make-pr-easy-to-review`. Their availability inside the two OpenCode leads still needs verification. The installed Pstack agents include the Thermo Nuclear Review subagent. The separate requested Review Agent still needs identification. Main PO must locate or enable the exact packages in both leads’ effective configuration and record their resolved names and revisions. Then confirm both Astra clients are on Medium and verify a Sol High lead and a XingChi Sol Max child in each lane. Model listing proves availability only; runtime effort and Pstack execution are still untested. Both session briefs are prepared; neither team received a feature prompt.

| Dry-run scenario | Result and owner |
|---|---|
| Two independent features at one base | The main PO exported A and B to separate trees from one dirty fixture checkout. B contained only B's edit. |
| Both teams request app.js | Tabletop gate held B's reservation. Main PO keeps A as sole writer until release or assigns B independent work. |
| Missing model, variant or named skill | Tabletop gate selects blocked. Main PO restores the exact capability and reruns only the affected preflight. |
| Independent reviewer reproduces a failure | Tabletop gate withholds publication. Builder fixes, reviewer retests, lane PO escalates repeated failure and main PO signs off the new candidate. |
| Unrelated staged and unstaged changes | Executed Git fixture. A contained exactly its edit, addition with a space in the name and deletion. The candidate preserved baseline B and dirty-file contents; HEAD, the real index and unrelated working changes were preserved. A directory manifest and an existing publication ref were refused. |

The Git exercise used a disposable repository. The review gates are procedural and require both POs to honor reservations. No provider settings changed, no production feature was dispatched and no GitHub PR was opened by the rehearsal.
