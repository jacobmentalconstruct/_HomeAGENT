# Workflow

This is the working pattern for all project work: tranches, repair passes, cleanups, and packaging. It exists so a fresh USER or AGENT can pick up the project without having to infer the rhythm from chat history.

## The Cycle

1. Observe the project and reconcile documented state with actual state.
2. Declare the current state.
3. Define the expected and required outcome, scope, and explicit non-goals.
4. Define the task list that maps the current state to that outcome.
5. Alert the user and pause while the tranche is still being planned.
6. If the user gives the go-ahead, implement only the declared tranche.
7. Consolidate the work and remove accidental complexity, temporary scaffolding, and ownership drift.
8. Verify the result against the declared outcome and acceptance criteria.
9. Review for bugs, frailties, stale assumptions, rough edges, inefficient logic, and missed small improvements inside tranche scope.
10. Fix what verification or review found, then reverify.
11. When documentation is approved or already in-scope, update stale docs and record the reason for the update.
12. Park the tranche with verification evidence, limitations, deferrals, and the next provisional step.
13. Reorient against the newly parked state before declaring the next tranche.
14. Move to the next planned step only after the user approves continuing.

## Addendums

- Keep tranches small. Tightly scoped work is easier to test, easier to park, and easier to resume.
- Keep every write boundary explicit: it should always be clear which participant may change what, and changes the user must approve go through an explicit approval step. Agents propose; approved operations act.
- Do not expand feature scope just because the code is warm. New behavior goes into the next tranche unless required to satisfy current acceptance criteria.
- Future tranches are provisional until reached; evidence from completed work may change the planned path.
- Changes of direction, tranche status, verification evidence, public or user-facing instructions, known limitations, deferrals, and stop criteria are recorded in the project record, not only in chat.
- Prefer proof over vibes. If a claim matters, capture a command, artifact, or limitation.
- Keep the README plain. It should help someone understand what this is without sounding like a generated product brochure.

## Parking Bar

A tranche is parked only when:

- The expected outcome is met or the limitation is named.
- Scope and non-goals remain intact, or any deviation is recorded.
- Relevant tests/checks have run, or skipped checks explain why.
- Verification evidence supports the tranche's completion claims.
- No background process needed by the tranche is still running.
- Temporary files are removed or classified as runtime artifacts.
- Documentation reflects the resulting state.
- The next step is short, concrete, provisional, and discoverable from docs.

## Working as a Team

- **One active tranche at a time.** It is declared in `PLAN.md` (Current work) by one AGENT, which then implements it. Other participants read and advise; they don't write to the repo during that tranche.
- **Approval is explicit.** The USER approves a declaration in words (chat or the product's UI). The implementing AGENT then records it in `PLAN.md` (Current work) as `Approved: T<n> (USER, <date>)`, and clears it when parking.
- **Record permission immediately.** As soon as the USER approves a tranche, record it in `PLAN.md` (Current work) before changing any code.
- **Track live progress.** Keep a `Progress:` checklist in `PLAN.md` (Current work) with one `- [ ]` / `- [x]` line for each scope task. Tick a task as soon as it is done, and keep a short `Now:` line current.
- **Commit each task.** On the tranche branch, make a commit as each scope task is completed, titled `T<n> wip: <task>` and ending with the trailer `Actor: AGENT`. Keep the final parking commit titled `T<n>: <outcome>`.
- **Declaring a tranche.** Write this in `PLAN.md` (Current work), keeping every part short:
  - ID and name;
  - expected outcome;
  - scope, as an ordered task list;
  - non-goals;
  - acceptance criteria, each one checkable by a command;
  - known risks.
- **Parking a tranche.** Add a short entry to the `PLAN.md` Log with:
  - outcome met, or the limitation named;
  - evidence: each command and its result;
  - limitations;
  - deferrals, which go into the `PLAN.md` Backlog;
  - next step.

  Then commit on the tranche branch, and wait for the USER to accept before merging into `main`.
- **Stuck or unsure:** stop, record the question in `PLAN.md` (Current work) under the declaration, and ask the USER. Don't widen scope to get unstuck.

## The Project Record in This Repo

There is no separate journal. The record is kept in three places, and nothing else:

| Step | Where it is recorded |
|---|---|
| 2 Declare state; 12 Park; 13 Reorient | `PLAN.md` Present and Current work. Parking adds a short entry to the `PLAN.md` Log: outcome, evidence (commands run and their results), limitations, deferrals, next step. |
| Decisions, deferrals, scope changes | `PLAN.md` Decisions and Backlog. |
| Branches | Each tranche is built on its own branch, `t<n>-<slug>` (e.g. `t0-skeleton`), and merged into `main` only after the user accepts the park. `main` always holds the last accepted state. |
| Proof over vibes | The command and its output summary go in the parked entry. The commit that parks a tranche is named `T<n>: <outcome>`, so `git log --oneline` reads as the tranche history. |
