# MainStem redesign proposal — the inbox model

Status: proposal, 2026-10-06. Step 1 (one status per review row) shipped with this document.

## How the board is actually used

Weeks of master-session traffic show one dominant loop and three side uses.

The dominant loop is reviews. A PR arrives, the agent reviews it, the comments get staged
on GitHub, the developer annotates and gives a verdict, the author responds, a reassess
runs, and the PR leaves. More than 80% of all requests the page sent were steps of this
loop. The side uses: answer a question about a review, jump to a session, and the daily
glance at tickets, calendar and mail.

The current design is organized by DATA SOURCE (panels: Reviews, Tickets, Sessions,
Worktrees, Log). The loop is organized by WHO ACTS NEXT. That mismatch is the noise: every
row shows all its facts because the layout does not know which fact matters now.

## The one rule

Every item on the board answers two questions in one line: **what is the status, and what
do I do?** One colored status, one action. Color = who acts:

| color | meaning | example |
| --- | --- | --- |
| amber (warn) | you act | "💬 guya replied — read it, then decide" |
| blue (info) | someone else acts | "⏳ waiting on the author" |
| green (good) | done | "✓ approved — done" |
| gray (neutral) | nothing to do | "✎ draft", "⌛ reviewing" |

Everything else — findings count, provenance, depth, agent confirmations, session
buttons — lives in the tooltip and the drawer card. A fact that does not change what you
do next does not get a pill.

## The inbox layout

Replace the panel stack with three stacked lists on Home:

1. **Needs you (N)** — every amber item from every source: reviews awaiting a verdict,
   staged pre-reviews, author replies, pending approvals, failing CI on your own PRs,
   due-today tickets. Sorted by age. This list IS the board; when it is empty, you are
   done.
2. **Waiting (N)** — collapsed by default. Blue items: posted reviews, delegated work,
   agents running. Each with who/what it waits for.
3. **Recently closed (N)** — collapsed. Green items from the last 48 h, for the
   "did that land?" glance.

Tabs stay for the inventories (Tickets, Sessions & work, Log), but Home stops being a
dashboard of panels and becomes the inbox.

## What gets deleted

- The agent-update gist pill on rows (the unread-replies chip and the drawer thread
  already carry it).
- The provenance pill (me/team/watch) — it becomes a filter, not a label.
- The depth pill (skim/read) — tooltip only.
- Verdict + findings-count as separate pills — folded into the one status phrase.
- "Start session" on rows — drawer only.
- The per-row defer/decision strips on Home — drawer only.

## Acceptance test

Open the board after two days away. Within ten seconds, without hovering, you can say
how many things need you and what the first three are. Nothing amber is a lie, and
nothing that needs you is hidden under gray.

## Steps

1. **Shipped**: review rows collapse to one status (this PR).
2. Same treatment for Tickets, My PRs and Sessions rows.
3. Build "Needs you" as a computed list over all sources; Home reorders to
   inbox-first. The panels move behind tabs.
4. Retire the counters that no longer earn their place in the header.

Each step is small and reversible; stop at any point and the board is still coherent.
