# ADR-0003: Planning domain foundation

- Status: Accepted
- Date: 2026-10-23

## Context

PomoPet currently stores executable work in `tasks` and focus history in `sessions`.
Planning MVP needs a long-lived hierarchy without breaking existing task IDs or session history:

```text
Goal -> month -> week -> day -> focus sessions
```

Only daily items are executable. Planning dates represent the user's local calendar, while audit
and session timestamps remain UTC.

## Decision

1. Add a `goals` table with title, definition of done, deadline, importance, status, weekly
   capacity, optimistic-lock version, and audit timestamps.
2. Keep the `tasks` table and extend it as the PlanItem store. Python may call these records plan
   items, but existing task/session integrations keep their IDs and table references.
3. A PlanItem has one of three horizons: `month`, `week`, or `day`. The only valid parent chain is
   month (goal root), week (monthly parent), and day (weekly parent).
4. An unscheduled day item is staged in Inbox and may optionally reference a goal without a weekly
   parent. Before a goal-linked item is scheduled, it must be attached to a weekly parent from the
   same goal. A general Inbox item may remain unlinked from any goal.
5. `planned_for` and `period_start` are ISO `YYYY-MM-DD` local dates. ISO weeks start Monday.
6. PlanItem status is `open`, `completed`, or `dropped`. Goal status is `active`, `completed`, or
   `archived`. Drop/archive retain descendants and focus history.
7. Existing `completed` remains synchronized for compatibility. New code uses PlanItem status as
   the lifecycle source of truth.
8. Focus sessions may start only for open daily items whose goal, when present, is active.
9. Progress sums completed session duration minus penalty time and rolls daily values up through
   week, month, and goal.
10. Mutations support an expected version. A stale version returns a conflict instead of silently
    overwriting a newer preview.

## Migration

The runtime migration is additive and repeatable. Legacy tasks are backfilled as unlinked daily
items with no planned date, preserving IDs, completion state, subtasks, and session references.
No table is dropped or renamed in this slice.

## Consequences

- Existing `/api/tasks` clients continue to operate on open daily items.
- The legacy delete operation now performs a soft drop.
- Structural integrity is enforced by the service layer because adding SQLite foreign-key and
  check constraints to the existing table would require a destructive table rebuild.
- A later migration may normalize PlanItem into a dedicated table only after MVP data migration
  and rollback procedures are proven.
