# The schema of five migrations that exist in no commit

**Recorded** 3 September 2026, immediately before the D23 reset.
**Why** The Neon development database was at `alembic_version = 0014` while the
migrations in this repository head at `0009`. Five migrations had been applied to
it from a working tree that is in no commit, no branch, no stash and no worktree
— all four were checked. Parul chose to reset the database to the repository's
head (`DECISIONS-REQUIRED.md` §5c, D23).

This file is the only surviving record of what those five migrations built. It is
kept because the work is **not throwaway**: `company_brain` is Phase 13's central
table and `question` / `question_choice` are Phase 7's question catalogue, so
whoever builds them should see this first rather than designing it twice.

**It is a record, not a specification.** Nothing here has a test, an ADR, or a
migration behind it. Treat every line as a prior attempt to be evaluated, not as
a decision already made.

## Method

`pg_dump` could not be used: the local client is 17.11, Neon runs Postgres 18.4,
and `pg_dump` refuses to dump from a newer server. So the two schemas were
introspected and diffed structurally — columns, constraints, indexes, policies,
and the row-security flags — against a database built from this repository's own
`db/bootstrap.sql` and migrations `0001`–`0009` (`scripts\db-ci.ps1`).

Row counts in the Neon database at the moment of the reset, all of it residue
from manual walkthroughs and smoke runs:

```
app_user            68     domain_claim        17     preview_session     14
tenant              48     user_session        93     everything else      0
```

No `workspace` row and no `membership` row existed, so no company had ever been
fully registered. Nothing that had to survive did not survive.

---

## 1. `company_brain` — new table

Versioned, with the current version enforced by a partial unique index rather
than a flag, and an honest unavailable state in the schema itself.

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `workspace_id` | uuid | no | |
| `version` | integer | no | `1` |
| `profile` | text | yes | |
| `products_services` | text | yes | |
| `target_customers` | text | yes | |
| `brand_voice` | text | yes | |
| `goals` | text | yes | |
| `competitors` | text[] | no | `'{}'` |
| `assumptions` | text[] | no | `'{}'` |
| `provenance` | text[] | no | `'{}'` |
| `generated_by` | text | no | `'model'` |
| `unavailable_reason` | text | no | `''` |
| `model_id` | text | yes | |
| `documents_read` | integer | no | `0` |
| `created_at` | timestamptz | no | `now()` |
| `superseded_at` | timestamptz | yes | |

```sql
PRIMARY KEY (id)
FOREIGN KEY (workspace_id) REFERENCES workspace(id) ON DELETE CASCADE
UNIQUE (workspace_id, version)                        -- uq_company_brain_version

CHECK (generated_by IN ('model','unavailable'))       -- ck_company_brain_generated_by
CHECK (generated_by <> 'unavailable'
       OR unavailable_reason <> '')                   -- ck_company_brain_unavailable_has_reason

CREATE UNIQUE INDEX ux_company_brain_current
    ON company_brain (workspace_id) WHERE superseded_at IS NULL;

ENABLE ROW LEVEL SECURITY;  FORCE ROW LEVEL SECURITY;
CREATE POLICY company_brain_workspace_isolation ON company_brain
    USING      (workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid)
    WITH CHECK (workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid);
```

**Worth keeping from this.** `ck_company_brain_unavailable_has_reason` puts ADR
0011 in the database: a Brain that says it could not be generated must say why,
and the constraint refuses the row otherwise. `ux_company_brain_current` means
"the current Brain" is a query rather than a flag anyone can forget to clear.
`generated_by` has no `'demo'` or `'sample'` value, which is right.

**Worth questioning.** `generated_by IN ('model','unavailable')` leaves no room
for a Brain assembled from calculators and documents with no model involved —
which under ADR 0011 is a supported state, not an unavailable one. `provenance`
as a bare `text[]` parallel to nothing is hard to join a citation to.

---

## 2. `question` and `question_choice` — new tables

A question catalogue that is code-owned by default and extensible per workspace,
with `workspace_id IS NULL` meaning global.

### `question`

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `key` | text | no | |
| `prompt` | text | no | |
| `stage` | text | no | |
| `answer_type` | text | no | |
| `scope` | text | no | `'L2'` |
| `department` | text | yes | |
| `asked_of` | text | yes | |
| `role_targets` | text[] | no | `'{}'` |
| `required` | boolean | no | `false` |
| `why` | text | no | `''` |
| `sink` | text | no | `'answer'` |
| `sort_order` | integer | no | `0` |
| `active` | boolean | no | `true` |
| `code_owned` | boolean | no | `false` |
| `created_at` | timestamptz | no | `now()` |
| `updated_at` | timestamptz | no | `now()` |
| `workspace_id` | uuid | yes | |

```sql
PRIMARY KEY (id)
FOREIGN KEY (workspace_id) REFERENCES workspace(id) ON DELETE CASCADE

CHECK (stage       IN ('pass_1','pass_2','department','connect','post_invite'))
CHECK (answer_type IN ('text','long_text','single_choice','multi_choice',
                       'ranked','money','url','user_list','file'))
CHECK (scope       IN ('L2','L3'))
CHECK (scope <> 'L3' OR department IS NOT NULL)       -- ck_question_l3_has_department
CHECK (department IS NULL OR department IN
       ('marketing','sales','finance','operations','hr','strategy','executive'))
CHECK (asked_of   IS NULL OR asked_of   IN (the same seven))
CHECK (role_targets <@ ARRAY['owner','executive','department_manager',
                             'contributor','viewer','external'])
CHECK (sink = 'answer')                               -- ck_question_sink

CREATE UNIQUE INDEX ux_question_global_key
    ON question (key)                WHERE workspace_id IS NULL;
CREATE UNIQUE INDEX ux_question_tenant_key
    ON question (workspace_id, key)  WHERE workspace_id IS NOT NULL;
CREATE INDEX ix_question_stage_order ON question (stage, sort_order);
CREATE INDEX ix_question_asked_of    ON question (asked_of);
```

Four policies rather than one, because a global question must be readable by
everyone while only a workspace's own rows may be written:

```sql
question_read   SELECT  USING (workspace_id IS NULL OR workspace_id = <the GUC>)
question_insert INSERT  WITH CHECK (workspace_id = <the GUC>)
question_update UPDATE  USING (workspace_id = <the GUC>) WITH CHECK (same)
question_delete DELETE  USING (workspace_id = <the GUC>)
```

### `question_choice`

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `question_id` | uuid | no | |
| `value` | text | no | |
| `label` | text | no | |
| `sort_order` | integer | no | `0` |

```sql
PRIMARY KEY (id)
FOREIGN KEY (question_id) REFERENCES question(id) ON DELETE CASCADE
UNIQUE (question_id, value)                           -- uq_question_choice_value
CREATE INDEX ix_question_choice_question ON question_choice (question_id, sort_order);
```

Its four policies reach through to the parent question rather than carrying a
`workspace_id` of their own:

```sql
USING / WITH CHECK (EXISTS (SELECT 1 FROM question q
                             WHERE q.id = question_choice.question_id
                               AND q.workspace_id = <the GUC>))
-- the SELECT policy also admits q.workspace_id IS NULL, for global questions
```

**Worth keeping from this.** The two partial unique indexes give global and
per-workspace keys their own namespaces without a nullable column in a unique
constraint. `why` as a non-null column says every question must justify itself to
the person answering it. `code_owned` distinguishes the catalogue the application
ships from what a workspace added.

**Worth questioning.** `CHECK (sink = 'answer')` is a one-value check — a
placeholder for a column that has no second value yet, which by this repo's own
standards should not exist until it does. The subquery policies on
`question_choice` are correct but cost a lookup per row; a denormalised
`workspace_id` would be the usual trade, and the choice was not recorded.
`asked_of` and `department` carry the same seven-value check without a comment
explaining how they differ.

---

## 3. Changes to existing tables

```sql
-- persona: three columns and one check
ALTER TABLE persona ADD COLUMN department text;   -- ck_persona_department, the seven
ALTER TABLE persona ADD COLUMN role_title  text;
ALTER TABLE persona ADD COLUMN stated_aim  text;

-- workspace: onboarding completion
ALTER TABLE workspace ADD COLUMN setup_completed_at timestamptz;

-- document: the value BUILD-STATUS records as missing
-- was ('pending','parsing','parsed','indexed','failed','quarantined')
-- became ('pending','parsing','parsed','indexed','superseded','failed','quarantined')
```

`document.ck_document_status` gaining `'superseded'` is exactly the fix Phase 1
schedules as **C2**, and it is why a local run against Neon would have passed a
defect the repository still has. `persona` gaining three columns is a partial
answer to **M5** — *persona: use it or drop it* — in the "use it" direction.

**`chunk.ck_chunk_review_state` was NOT changed.** Both databases carry
`('auto_approved','pending_review','approved','rejected')`; the drift in **C1** is
between that constraint and the Python `ReviewState` enum, and it is untouched
here. Phase 1 still has to reconcile it.

---

## 4. What this means for the phases ahead

| Phase | Item | What this record changes |
|---|---|---|
| P1 | **C2** — add `'superseded'` | Already designed, exactly as planned. Write the migration and the test |
| P1 | **C1** — `review_state` | Unaffected. Neither database was ever changed here |
| P1 | **M5** — persona | Somebody chose "use it". Three columns, one check. Not a decision until Parul makes it |
| P5 | `workspace.setup_completed_at` | The onboarding spine needs a completion marker; here is one shape for it |
| P7 | `question` / `question_choice` | A full catalogue design, with the global-versus-workspace namespacing already solved |
| P13 | `company_brain` | A versioned table with an honest unavailable state and a current-version index |

The migration numbers `0010`–`0014` are free again after the reset, so Phase 1's
migration is `0010` as `doc/12` assumes.
