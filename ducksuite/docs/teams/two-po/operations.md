# DuckSuite feature lanes

The main PO edits this register before dispatch. Keep two rows. Put the detailed spec, test commands and review findings in the linked feature brief/review. Use repository-relative filenames in the reservation, including tests, new files and both names of a rename. Shared working docs and the report belong to the main PO, who folds their updates into each candidate serially.

| Lane | PO | Feature / brief | Base | Reserved files | Lead session | Acceptance / state |
|---|---|---|---|---|---|---|
| A | Main Codex, GPT-6.2 Astra, Medium | Unassigned | — | — | — | Setup only · gated |
| B | Second Codex, GPT-6.2 Astra, Medium | Unassigned | — | — | — | Setup only · gated |

## Preflight and reservations

1. Work in `/Users/happynghia/Public/Project/Code/drop_eval/ducksuite`. Verify with `pwd -P` and `git rev-parse --show-toplevel`. Main PO captures the integration base SHA, current branch, dirty and staged paths before reserving work. Preserve pre-existing changes, including untracked agent config. Keep the original checkout on `ducksuite`. Claude and both Codex POs work here. The main PO assigns each OpenCode lead a code-only worktree and a feature branch based on the recorded integration SHA. Record its actual path and branch in the lane register before dispatch.
2. Reserve disjoint feature paths, including tests. Each lead edits only the assigned source files. The main PO records commits in the assigned worktree. Keep all environments, caches, scratch data, app bundles and packaging in the original checkout’s build directory. Lane scratch directories there are A and B under build/two-po, on ports 8831 and 8832. Share the existing toolchain. Do not copy a build folder into a worktree.
3. In DuckSuite run `opencode models` and require exact entries `openai/gpt-6.2-sol` and `xingchi/gpt-6.1-sol`. Confirm high and max are selectable on the respective providers. Check the effective model AND effort for both Astra POs in their clients. Expect Medium. Resolve each named skill/command in the environment where it will run. Record its exact invocation, package/source and version or revision. Similar names do not satisfy this check.
4. Bind service reads explicitly. The following safe probe prints only the directory. Plain API calls on this machine can resolve to the home directory. Verify the same directory on each actual session before sending project context. Never print provider configuration, request headers containing credentials or session transcripts into the register.

   ```sh
   opencode api GET /api/provider --header "x-opencode-directory:$PWD" |
     python3 -c 'import json,sys; print(json.load(sys.stdin)["location"]["directory"])'
   ```

5. Gate **feature dispatch** on all requested components. Once resolved, create two uniquely titled leads, one per lane, from their registered code worktrees using the build agent and `-m 'openai/gpt-6.2-sol#high'`. Use a short preflight-only message first. Confirm the directory and effective runtime model/effort from the lead and one probe child (`xingchi/gpt-6.1-sol#max`). Record session IDs and evidence before sending a feature brief. Independently confirm each team; a successful probe in A does not establish B’s settings. Resume by explicit ID only. Check the service state before sending; if a client disconnects, inspect that session before retrying. Never send a second prompt to a busy lead.

## Two dispatch briefs

**Lane A, main PO → lead A.** “You lead DuckSuite lane A. Use only the checkout, base, files and acceptance checks in register A. Edit in your assigned code worktree. Main PO runs integrated checks in the original folder. Use Grill Me for unresolved product decisions. Use Pstack Swarm to fan out independent investigations, tests and disjoint implementation to XingChi GPT-6.1 Sol at Max. Give each child a written scope and relevant skill. Record session, effective model/effort, files and result. Return evidence to the main PO. No Git writes.”

**Lane B, second PO → lead B.** “You lead DuckSuite lane B. Use only register B’s feature and files at its pinned base. Edit in your assigned code worktree. Main PO runs integrated checks in the original folder. Follow the same Grill Me, Pstack Swarm, model verification and reviewer gates as A. Report to the second PO, who hands the candidate to the main PO. Request a changed reservation before touching any shared file. No Git writes.”

Both briefs inherit the founder-media, archive and app restrictions in AGENTS.md. Don’t dispatch footage, secrets or founder data to any model. Use the lane scratch core for tests. If a brief needs a founder check, specify the exact interaction and expected outcome.

## Review and handoff

- The lane PO settles intent and acceptance before coding. The lead runs **Pstack Thermo Nuclear Review** and **Review Agent** independently of the implementer. Each finding names a file, impact and reproduction. **Loop Me** routes it back to its owner for a fix, regression test and independent retest. A failed check holds publication. If the same failure returns twice, the lane PO revises the approach before another attempt.
- Hand off the base SHA, reserved paths, actual changes, tests/results, open findings and founder-only checks. The main PO uses **Code Review** on the pinned-base diff for spec and standards; use **Impeccable** for rendered UI, interaction, keyboard access and layout. Claude may advise on escalations. The main PO records sign-off for the exact candidate SHA. Any change after sign-off needs verification again.
- On launch failure record the missing capability and responsible PO. Resume the missing check only after configuration changes. No automatic provider, model, effort or skill substitutions.

## Publish a single lane

1. Freeze the feature changes. The main PO reviews the branch diff against its pinned base, confirms file ownership and records the accepted commit. Use Pstack Make PR Easy to Review for the commit and PR description.
2. Integrate one reviewed commit or branch at a time. In the original folder verify the branch is `ducksuite` and the index and tracked files are clean. Preserve unrelated untracked files. Start a `git merge --no-ff --no-commit` of the accepted branch. Resolve any conflicts with the feature owner before proceeding.
3. Run the brief’s acceptance checks, the full pytest suite and the JS syntax check against the pending merge in this original folder. Build the app here when required. On failure, return findings to the owner and abort the pending merge before taking another feature. On pass, finalize the merge and record verification in the loop review. Publish against ducksuite according to the release brief. Release the reservation.
