# Demo and reusable graphics

The MP4 is an actual browser recording of the saved-data demo canvas. It shows
the five revised-objective runs on one clock, followed by the same before/after
chart used in the thread and repository. No new traffic or model output was
generated for the recording. It is silent, with readable text baked into the
frames. An optional descriptive caption file is included.

| Asset | Use |
| --- | --- |
| [demo.mp4](demo.mp4) | Post 1; GitHub release/README demo |
| [demo-poster.png](demo-poster.png) | Video poster and README preview |
| [Experiment overview](01-experiment-overview.png) | Post 2; experiment documentation |
| [Before/after results](02-before-after-results.png) | Post 5; findings section |
| [Objective explained](03-objective-explained.png) | Post 4; methodology section |
| [Accessible descriptions](../marketing/alt-text.md) | Attachment alt text and video description |

Each graphic also has SVG and PDF versions. Source data are in
`data/published/traffic-objective-v2/`; the three figures regenerate with:

```sh
.venv/bin/python scripts/render_marketing_figures.py
```

To make another browser recording:

1. Run `python3 scripts/serve_saved_demo.py` and open `http://127.0.0.1:8766/`.
2. Keep the demo tab visible. Click **Record browser demo** and wait for the
   download link. This captures the page's canvas, not the desktop or browser chrome.
3. Download the recording and convert it:

```sh
.venv/bin/python scripts/convert_demo_recording.py /path/to/downloaded-recording.mp4
```

The converter also accepts WebM when that is the browser's available format.
It produces a 1920×1080, 24 fps, H.264/yuv420p MP4 with fast-start metadata,
a poster, and a full-decode verification record. The demo is approximately
42 seconds: 4 s introduction, 30 s synchronized playback at 4×, and 8 s chart.
The duration and file size fit the standard non-Premium upload limits listed
in [X's video guidance](https://help.x.com/en/using-x/x-videos).

The moving mean system-time counter includes cars scheduled by the displayed
time. Remaining demand is total 78 minus completed, including future scheduled
cars. At the 120-second cutoff the counters match the published episode
summaries. The comparison chart includes both objectives; the moving panels
show only the revised objective.
