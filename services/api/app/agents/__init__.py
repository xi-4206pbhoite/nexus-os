"""Agents. Model-facing work, and the boundary that keeps it safe.

Depends on `app.ai.contracts.LlmProvider` and never on a vendor SDK —
`tests/test_ai_boundary.py` walks every file outside `app/ai/` and fails the build
on a vendor name, which has already caught one docstring.

Two rules shape everything here:

- **I7** — foreign content reaches a prompt only through `untrusted.wrap_untrusted`,
  and a turn that read any is tainted for its whole life.
- **I1** — an agent produces prose and preferences. Anything that is a *figure* is
  computed elsewhere, in code, from data that was fetched.
"""
