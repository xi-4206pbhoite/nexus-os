"""Marketing is not scoreable without GA4, and the audit scores must not fill in.

`doc/05` §3.1 and `doc/12` P16. The temptation this guards against is specific
and reasonable-looking: the brand and technical-SEO audits produce real numbers
from a real crawl, Marketing has no other score, and averaging them would give
the dashboard something to show.

It would be wrong, and quietly so. Those scores measure **the website** —
whether the title tags are sensible, whether the pages load. Marketing
performance is whether anybody arrived and what they did. A company with an
immaculate site and no visitors would score well on a metric named for the thing
it is failing at, and nothing on the screen would say so.
"""

from __future__ import annotations

from app.domain.dashboards import Source
from app.domain.registry import (
    REQUIRED_FOR_SCORING,
    score_denominator,
    scoreable_departments,
)
from app.domain.scopes import Department

RUNS_EVERYTHING = frozenset(Department)


def test_marketing_is_excluded_from_the_score_without_ga4() -> None:
    """The named test from `doc/12` P16."""
    without = scoreable_departments(RUNS_EVERYTHING, connected=frozenset())
    assert Department.MARKETING not in without

    with_ga4 = scoreable_departments(RUNS_EVERYTHING, connected=frozenset({Source.GA4}))
    assert Department.MARKETING in with_ga4


def test_the_denominator_shrinks_rather_than_the_score_dropping() -> None:
    """The distinction that makes the number honest.

    Marketing being unscoreable must make the denominator smaller, not the
    numerator. Scoring it as zero would report a failure; excluding it reports
    an absence, and only the second is true.
    """
    without = score_denominator(RUNS_EVERYTHING, connected=frozenset())
    with_ga4 = score_denominator(RUNS_EVERYTHING, connected=frozenset({Source.GA4}))

    assert with_ga4 == without + 1


def test_another_connector_does_not_unlock_marketing() -> None:
    """Only GA4 does. A connected CRM says nothing about whether anybody visited
    the website."""
    other = scoreable_departments(RUNS_EVERYTHING, connected=frozenset({Source.DOCUMENTS}))
    assert Department.MARKETING not in other


def test_no_other_department_carries_a_connector_requirement() -> None:
    """Asserted so adding one is a deliberate act.

    A requirement added quietly here would remove a department from somebody's
    score with no visible cause — their number would change and nothing would
    explain it.
    """
    assert set(REQUIRED_FOR_SCORING) == {Department.MARKETING}


def test_omitting_connector_information_reports_the_structural_answer() -> None:
    """A caller that does not know what is connected gets what the registry can
    honestly say, rather than a guess in either direction. Callers that do know
    pass it and get the narrower, truer answer."""
    assert Department.MARKETING in scoreable_departments(RUNS_EVERYTHING)


def test_the_audit_scores_are_not_a_marketing_score() -> None:
    """`calculators/audit.py` says this in its own docstring; this makes it a
    test. The audits are per-category and stay that way — there is no function
    that combines them, and this fails if somebody adds one.
    """
    import app.calculators.audit as audit

    combined = [
        name
        for name in dir(audit)
        if name.startswith(("marketing_score", "overall_score", "combined"))
    ]
    assert not combined, (
        f"{combined} would merge website audits into a Marketing score. Those "
        "measure the site; Marketing performance is whether anybody arrived."
    )
