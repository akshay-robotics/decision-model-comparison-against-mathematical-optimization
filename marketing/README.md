# X and GitHub release kit

Main finding: **Changing the objective changed controller behavior, but did not
improve every controller.** Frame this as an early experiment in decisions over
a planning horizon. The featured revised-objective comparison is at 15 seconds;
it does not establish general long-horizon optimization ability.

## Ready-to-use files

- [Five-post thread](thread.md) and [structured post copy](thread.json).
- [42-second MP4](../media/demo.mp4), [poster](../media/demo-poster.png), and
  [optional descriptive captions](../media/demo.srt).
- Three graphics in the [media folder](../media/README.md), each as PNG/SVG/PDF.
- [Accessible descriptions](alt-text.md).
- [Small published dataset](../data/published/traffic-objective-v2/README.md),
  exact prompts, verified source snapshots, and figure-generation scripts.
- Project README, setup instructions, `.env.example`, and MIT license.

## Publish sequence

Post 1 gets the video; post 2 the overview; post 3 is text-only; post 4 gets the
objective explanation; post 5 gets the before/after chart. Add the descriptions
from `alt-text.md`. The video is silent with baked-in labels and a shared clock.
All posts are below the standard 280-character budget before adding a URL.

The video was recorded from the browser's saved-data demo canvas and checked
for duration, codec, dimensions, and decode errors. Its approximately 42-second
duration and small file size fit the standard limits documented in
[X's video guidance](https://help.x.com/en/using-x/x-videos).

## Claim boundaries

- Original and revised traffic results are paired by the same seed and demand,
  not by identical later observations. State values diverge after actions.
- No model returns a full plan in this comparison; each outputs NS or EW.
- The revised objective adds a fixed terminal-queue penalty. Do not call it a
  direct trip-completion reward or a generally validated objective.
- The older frozen optimization scores do not certify revised-objective model
  output. No new frozen benchmark was run under the revised objective.
- Gurobi's optimality claim applies to its simplified queue model, not optimal
  overall SUMO traffic behavior. One seed cannot support a general model ranking.
- Do not claim real-time traffic operation: SUMO pauses during model calls.

## GitHub publication

The selected public repository is
[`akshay-robotics/decision-model-comparison-against-mathematical-optimization`](https://github.com/akshay-robotics/decision-model-comparison-against-mathematical-optimization).
Use that URL when sharing the work and recheck post length. The same MP4 and PNG files
can be uploaded as GitHub release assets. A GitHub attachment URL can be used
for native inline video playback in the README after upload; its current
poster links to the committed MP4.

Before publishing, run `scripts/check_repository.py`,
`scripts/check_publication_security.py`, and
`scripts/validate_release.py`, review the complete file list, and retain the
limitations and license. Raw local results, API credentials, downloaded papers,
and third-party model/dependency binaries remain excluded.
