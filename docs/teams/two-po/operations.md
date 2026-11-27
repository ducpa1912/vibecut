# DuckSuite feature lanes

The main PO edits this register before dispatch. Keep two rows. Put the detailed spec, test commands and review findings in the linked feature brief/review. Use repository-relative filenames in the reservation, including tests, new files and both names of a rename. Shared working docs and the report belong to the main PO, who folds their updates into each candidate serially.

| Lane | PO | Feature / brief | Base | Reserved files | Lead session | Acceptance / state |
|---|---|---|---|---|---|---|
| A | Main Codex, GPT-6.2 Astra, Medium | Unassigned | — | — | — | Setup only · gated |
| B | Second Codex, GPT-6.2 Astra, Medium | Unassigned | — | — | — | Setup only · gated |

## Preflight and reservations

1. Work in `/Users/happynghia/Public/Project/Code/drop_eval/ducksuite`. Verify with `pwd -P` and `git rev-parse --show-toplevel`. Main PO captures the integration base SHA, current branch, dirty and staged paths before reserving work. Preserve pre-existing changes, including untracked agent config. Use one batch branch from the integration base. Only the main PO stages, changes refs, commits, pushes or opens PRs. Keep that branch checked out until both lanes release their reservations.
2. Main PO compares paths and feature dependencies. A file has one writer across both teams. Within a lane the lead assigns each file to one builder. If both need app.js, one lane owns it; the other tests, investigates or takes an independent feature. Order dependent features, pinning the second base after integration. Record each lane’s acceptance command and PO before sending a prompt. Lane A uses port 8831 and build/two-po/A; B uses 8832 and build/two-po/B. Keep build outputs separate too.
3. In DuckSuite run `opencode models` and require exact entries `openai/gpt-6.2-sol` and `xingchi/gpt-6.1-sol`. Confirm high and max are selectable on the respective providers. Check the effective model AND effort for both Astra POs in their clients. Expect Medium. Resolve each named skill/command in the environment where it will run. Record its exact invocation, package/source and version or revision. Similar names do not satisfy this check.
4. Bind service reads explicitly. The following safe probe prints only the directory. Plain API calls on this machine can resolve to the home directory. Verify the same directory on each actual session before sending project context. Never print provider configuration, request headers containing credentials or session transcripts into the register.

   ```sh
   opencode api GET /api/provider --header "x-opencode-directory:$PWD" |
     python3 -c 'import json,sys; print(json.load(sys.stdin)["location"]["directory"])'
   ```

5. Gate **feature dispatch** on all requested components. Once resolved, create two uniquely titled leads, one per lane, from this checkout using the build agent and `-m 'openai/gpt-6.2-sol#high'`. Use a short preflight-only message first. Confirm the directory and effective runtime model/effort from the lead and one probe child (`xingchi/gpt-6.1-sol#max`). Record session IDs and evidence before sending a feature brief. Independently confirm each team; a successful probe in A does not establish B’s settings. Resume by explicit ID only. Check the service state before sending; if a client disconnects, inspect that session before retrying. Never send a second prompt to a busy lead.

## Two dispatch briefs

**Lane A, main PO → lead A.** “You lead DuckSuite lane A. Use only the checkout, base, files and acceptance checks in register A. Work under build/two-po/A on 8831. Use Grill Me for unresolved product decisions. Use Pstack Swarm to fan out independent investigations, tests and disjoint implementation to XingChi GPT-6.1 Sol at Max. Give each child a written scope and relevant skill. Record session, effective model/effort, files and result. Return evidence to the main PO. No Git writes.”

**Lane B, second PO → lead B.** “You lead DuckSuite lane B. Use only register B’s feature and files at its pinned base. Work under build/two-po/B on 8832. Follow the same Grill Me, Pstack Swarm, model verification and reviewer gates as A. Report to the second PO, who hands the candidate to the main PO. Request a changed reservation before touching any shared file. No Git writes.”

Both briefs inherit the founder-media, archive and app restrictions in AGENTS.md. Don’t dispatch footage, secrets or founder data to any model. Use the lane scratch core for tests. If a brief needs a founder check, specify the exact interaction and expected outcome.

## Review and handoff

- The lane PO settles intent and acceptance before coding. The lead runs **Pstack Thermo Nuclear Review** and **Review Agent** independently of the implementer. Each finding names a file, impact and reproduction. **Loop Me** routes it back to its owner for a fix, regression test and independent retest. A failed check holds publication. If the same failure returns twice, the lane PO revises the approach before another attempt.
- Hand off the base SHA, reserved paths, actual changes, tests/results, open findings and founder-only checks. The main PO uses **Code Review** on the pinned-base diff for spec and standards; use **Impeccable** for rendered UI, interaction, keyboard access and layout. Claude may advise on escalations. The main PO records sign-off for the exact candidate SHA. Any change after sign-off needs verification again.
- On launch failure record the missing capability and responsible PO. Resume the missing check only after configuration changes. No automatic provider, model, effort or skill substitutions.

## Publish a single lane

1. Lane writers freeze their accepted paths. Main PO inspects the pinned-base diff for those paths and reserves the documentation updates for this lane. Both POs confirm no overlapping ownership. Pre-existing changes to a reserved file require an explicit split or reschedule.
2. Run `scripts/lane-tree.sh "$base" file1 file2 ...`. The temporary index starts from the pinned base. The command includes explicit owned additions, edits and deletions and emits a tree ID. Review `git diff --name-status "$base" "$tree"` against the manifest, then review the full diff. Stop on any surprise.
3. Create the candidate with `git -c commit.gpgsign=false commit-tree "$tree" -p "$base" -F "$message_file"` and keep its returned SHA. Extract `git archive "$sha"` into a fresh ignored build/candidates directory in this checkout. Run the feature checks, pytest and node syntax checks **there**, with lane-specific scratch data, the approved toolchain and any required ignored dependencies supplied explicitly. Confirm imports resolve to candidate source. Record unavailable bundle or founder tests. A mixed-tree run is advisory.
4. Following sign-off, use **Pstack Make PR Easy to Review** for the commit message and PR description (regenerate and verify the candidate SHA if the message changes). Main PO creates a fresh feature ref using `git update-ref refs/heads/feature/<lane-feature> "$sha" ""`; this fails if the ref already exists. Push that explicit ref over the repo’s HTTPS remote and open a PR with base `ducksuite`. Include user-visible behavior, review order, tests and founder checks. A moving integration base requires testing the merge result before integration. Never switch the shared checkout while a lane is active. Close reservations after publication; reconcile the batch branch with integration only when both lanes are idle.
