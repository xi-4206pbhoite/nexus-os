# Archive — retired working documents

Nothing here is current. Each file was accurate when written and has been
superseded by a document that is maintained. Kept because a decision is easier
to trust when you can see what it replaced.

| File | What it was | Superseded by | Why retired |
|---|---|---|---|
| `ARCHITECTURE.md` | The architecture proposal written before any production code, 16 Aug 2026. Its §0 precedence reading, §3 permission model, §4 untrusted boundary and §5 execution modes are all still correct and were carried forward verbatim in substance | `ARCHITECTURE-HLD.md` and `ARCHITECTURE-LLD.md` | One document mixed system shape with implementation detail, and it described an intended system rather than the built one. Split, and reconciled against the code |
| `TASKS.md` | The M0–M13 task breakdown expanded from doc 07 §6 | `VISION-AND-PLAN.md` (phases and definition of done) and `BUILD-STATUS.md` §13 (the prioritised work list with IDs) | Five of its `[x]` entries were contradicted by the code — see `BUILD-STATUS.md` appendix. A tracker that overstates completion is worse than none |
| `MILESTONE-0.md` … `MILESTONE-5.md` | Per-milestone completion notes, one per milestone as doc 07 §5.2 required | `BUILD-STATUS.md` | They record what was believed complete at the time. `BUILD-STATUS.md` records what is verifiably complete now, and corrects them where they differ |

## What replaced the milestone-note habit

Doc 07 §5.2 asked for a `MILESTONE-N.md` at the end of each milestone. That
practice produced six documents that agreed with each other and disagreed with
the database. The replacement rule is in `VISION-AND-PLAN.md` §7:

> A phase is complete when its acceptance test has run green in CI against a real
> Postgres, driven through the application rather than around it. The evidence is
> the CI run, not a note.

`BUILD-STATUS.md` is regenerated at the end of each phase rather than appended to.

---

*Retired 25 August 2026, in the documentation reorganisation that produced
`VISION-AND-PLAN.md`, `ARCHITECTURE-HLD.md` and `ARCHITECTURE-LLD.md`.*
