"""Score train (ported from TournamentHigscore): milestone progress of the cumulative total score.

The "train" is a progress bar that advances as the summed score of all games
climbs toward a sequence of milestones. This module is a pure, in-process
computation fed by the already-fetched total score — it issues no queries.
"""

from nestris_ltm.core.bracket import ScoreTrain

# The train advances toward milestones spaced one million apart, without limit:
# 1M, 2M, 3M, … — the next target is always the next million above the total.
STEP = 1_000_000


def compute_train(total_score: int) -> ScoreTrain:
    """Compute milestone progress for a given cumulative ``total_score``.

    Milestones are every ``STEP`` (1,000,000). ``current_milestone`` is the last
    million reached (0 below 1M), ``next_milestone`` is the next million (always
    set — the train never finishes), and ``progress`` is a 0.0..1.0 fraction
    within the current million segment.
    """
    total_score = max(0, total_score)
    current = (total_score // STEP) * STEP
    next_milestone = current + STEP
    progress = round((total_score - current) / STEP, 4)

    return ScoreTrain(
        total_score=total_score,
        current_milestone=current,
        next_milestone=next_milestone,
        progress=progress,
        # The next few million markers (purely informational; the bar uses
        # current/next/progress).
        milestones=[next_milestone, next_milestone + STEP, next_milestone + 2 * STEP],
    )
