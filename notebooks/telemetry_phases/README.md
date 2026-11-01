# Telemetry phase estimation: pre-infusion and shot time

**Status:** implemented in v0.11.0 (2026-11-01): see §8. Decisions from
the first review are recorded in §7; the one-time data remediation is in §9.
**Data:** all 185 shots with telemetry as of 2026-11-01.

## Goal

Estimate two durations from each shot's telemetry:

| Quantity | Definition | Boundaries |
|---|---|---|
| **Pre-infusion** | pressure first rises → flow begins | `t_pump_on` → `t_flow_on` |
| **Shot time** | flow begins → pressure is removed | `t_flow_on` → `t_pump_off` |

Each boundary is found by fitting ideal curve segments on either side of a
transition and taking the point where they intersect.

## 1. What the telemetry looks like

| | Beanconqueror | Brewmeo (CSV import) |
|---|---|---|
| Shots | 101 (Apr–Sep 2026) | 84 (Sep–Nov 2026) |
| Series used | `pressureFlow.actual_pressure`, `weight.actual_smoothed_weight` | same (converted by `brewmeo_import`) |
| Sampling | ~10 Hz, `brew_time` in `S.T` tenths notation | ~10 Hz |
| Recording starts | before the pump (pressure = 0) | **auto-starts at ~0.85 bar**; 56 of 84 start at 0.8–0.9 bar |

Every shot here is from the ECM Synchronika II, and 175 of the 185 are logged
as `5+3` pre-infusion. The pressure trace has a consistent shape (see the
figure below):

1. **Pump on.** Pressure rises from 0 to a low line-pressure plateau of about
   1–2 bar. This is the manual pre-infusion.
2. **Ramp.** About 7 s later, pressure climbs steeply to about 9 bar.
3. **Plateau.** Pressure slowly declines as the puck erodes. On flow-taper
   shots the user eases it down to about 1 bar.
4. **Pump off.** A near-vertical drop to 0.

Weight stays flat at the tare until the first drips, then rises along a
convex curve. Flow (`realtimeFlow`) is the derivative of weight, so it is
noisier and carries no extra information. The estimates below fit weight
directly.

**Data quality issues:**

- **7 truncated recordings** (Brewmeo; shots 657, 658, 660, 664, 668, 687,
  705) start at 8–9 bar, partway through the shot. Neither boundary at the
  start can be recovered.
- **1 recording has no pressure data** (shot 706).
- **Brewmeo recordings that auto-start** miss the pump-on edge. For these 63
  shots, `t_pump_on` has to be imputed (see §3).
- **Occasional weight spikes** from a bumped cup or scale. A 5-sample
  running median removes them.
- **Shot 606:** the scale log interpolates linearly out to 200 s, so the
  shot is mostly unusable.

![Fitted segments on 12 shots spread across the date range](figures/fit_examples.png)

## 2. Method: two-segment fits at each transition

Every boundary uses one generic routine, `fit_breakpoint` in
[`phase_fit.py`](phase_fit.py). It fits a **continuous two-segment curve** by
least squares:

- left segment: a constant, or a line;
- right segment: a polynomial in `(t − t0)`;
- a grid search over the knot `t0` (0.05 s steps) picks the best fit.

Because the two segments are joined at `t0`, the knot *is* their
intersection point.

| Boundary | Signal and window | Left segment | Right segment |
|---|---|---|---|
| `t_pump_on` | pressure, from the start until pressure reaches 70% of the pre-infusion plateau | flat baseline | rising line |
| `t_ramp` *(context only)* | pressure, from pump on + 0.5 s until pressure reaches 60% of peak | sloped plateau line | ramp line |
| `t_flow_on` | weight, from pump on until the cup holds 4 g | flat baseline (tare) | **quadratic** rise |
| `t_pump_off` | pressure, from 2 s before the last sample above 0.7 bar until pressure reaches 0 | sloped (declining) plateau line | steep drop line |

Two design choices came out of reviewing the first fits:

- **Pump-off uses an absolute 0.7 bar level, not a fraction of peak.** On
  flow-taper shots, pressure falls gradually from 8 to about 1 bar and only
  then drops to 0. An early version keyed on 50% of peak. It cut taper shots
  in the middle of the taper, 5–10 s early.
- **Flow-on uses a quadratic rise, not a tangent line.** Weight accelerates
  as flow builds, so a straight line fitted to the rise is too shallow. It
  puts the intersection late, and how late depends on how much of the rise
  the window includes. See the sensitivity table in §4.

## 3. Imputing pump-on for Brewmeo auto-start recordings

63 usable Brewmeo shots begin at about 0.85 bar, after the pump has already
started. Two calibrations were tested. Both use the 110 recordings that
captured the pump-on edge:

| Calibration | Assumption | Offset (median, IQR) | Imputed pre-infusion (median, IQR) |
|---|---|---|---|
| **Level** | the time to reach ~0.85 bar is the same on every shot | 2.65 s (2.25–3.69) | 10.6 s (8.8–12.6) |
| **Ramp-aligned** | pump on → ramp takes the same time on every shot (the manual routine) | 7.05 s (6.60–7.89) | 10.4 s (9.2–13.0) |

Both give about the same answer, and both agree with the 104 shots where
pump-on was measured directly (median **9.95 s**, IQR 9.25–11.4). The spread
is larger for imputed shots (SD 4.4 s vs 2.2 s). At least part of that is
real. Ramp → flow on does not depend on pump-on at all, and its SD also
widens, from 2.3 s before mid-September to 4.0 s after. The rest is
imputation noise. The current code uses the level calibration.

## 4. Results

### Validation: fitted shot time matches the logged extraction time

The logged `extraction_time` is entered by hand from a timer. It turns out
to measure **flow on → pump off**, the same thing the fitted shot time
measures:

| Maker | n | logged − fitted shot time, median (IQR) | logged − fitted *total* time, median |
|---|---|---|---|
| Scott | 137 | +1.3 s (+0.15 to +2.3) | −9.0 s |
| Sara | 30 | +0.9 s (+0.06 to +1.9) | −9.5 s |

- **81%** of the 167 usable shots agree within ±3 s, and 64% within ±2 s.
- Logged times run about 1 s longer than fitted times. That is consistent
  with starting the timer at the first visible drip, slightly before the
  extrapolated stream onset, or stopping it a moment after the pump stops.
- Flow-taper shots: 74% within ±3 s, compared with 83% for the rest.

![Logged vs fitted shot time (left) and total time (right)](figures/logged_vs_fitted.png)

### Distributions

| Quantity | n | median | IQR |
|---|---|---|---|
| Pre-infusion, pump-on measured | 104 | 9.95 s | 9.25–11.4 |
| Pre-infusion, pump-on imputed | 63 | 10.6 s | 8.8–12.6 |
| Shot time | 167 | 29.2 s | 25.3–33.6 |
| Pump on → ramp | 110 | 7.05 s | 6.6–7.9 |
| Ramp → flow on | 167 | 2.95 s | 1.7–4.4 |

The logged `5+3` lines up with these components. Pump on → ramp is about 7 s
(the "5" plus the time to open the paddle), and ramp → flow on is about 3 s
(the "+3"). Ramp → flow on does not depend on pump-on at all, so it is also
available for the auto-start Brewmeo shots.

![Distributions](figures/distributions.png)
![Pre-infusion over time](figures/pre_infusion_over_time.png)

### Flow-onset sensitivity

Agreement with the logged time for each choice of rise segment and fit
window:

| Rise segment | window ends at | median logged − fitted | median abs diff | within ±3 s | median measured pre-infusion |
|---|---|---|---|---|---|
| line (tangent) | 2 g | +1.65 | 1.90 | 74% | 10.2 s |
| line (tangent) | 4 g | +2.00 | 2.15 | 67% | 10.75 s |
| line (tangent) | 8 g | +3.03 | 3.08 | 47% | 11.5 s |
| **quadratic** | 2 g | +0.90 | 1.45 | 81% | 9.8 s |
| **quadratic** | **4 g (chosen)** | +1.25 | 1.55 | 80% | 9.95 s |
| quadratic | 8 g | +0.88 | 1.40 | 79% | 9.7 s |

The quadratic fit is stable whatever the window. The tangent-line fit drifts
later as the window widens.

## 5. Where it disagrees, and why

11 of Scott's shots differ from the logged time by more than 5 s:

| Pattern | Shots | Likely cause |
|---|---|---|
| Logged value is a typo | 363 (logged 96, fitted 36.7) | Data entry. The telemetry could catch this at save time. |
| Logged ≈ ramp → pump off | 289, 330, 431, 465 (Apr–Jul) | The timer was started at the ramp, not the first drip. 330, 431 and 465 are profiled shots (§6); the fitted pump-off on them is correct. |
| Long, slow drip before a steady stream | 569, 656, 661 | Fine grind or slow start. Flow on is the start of the steady stream (decision 2 in §7), so the drip phase counts as pre-infusion. |
| Early drips during pre-infusion | 681, plus 8 flagged `flow_before_ramp` | Real channel or drip flow before the ramp. Pre-infusion comes out short (2–6 s). |
| Other | 458, 466 | Not investigated. |

Other flags: `low_peak_pressure` (336, 412, 713) marks shots that never
reached 6 bar. All three are Flow Taper shots (§6), and the fits still look
reasonable on them.

![Flagged and disagreeing shots](figures/problem_shots.png)

## 6. Profiled shots

On a normal shot, pressure declines slowly and smoothly as the puck erodes.
On a profiled shot (the app's **Flow Taper** flag), the pressure is
deliberately modulated during the shot: typically eased from about 9 bar
down to about 1 bar, held there, and only then cut.

**The phase estimator handles profiled shots without changes.** Pump-off is
found as the final drop to zero (the 0.7 bar rule in §2), so the
deliberate taper is never mistaken for pump-off. Flow on and pump on happen
before any modulation starts.

**Profiling can be detected from the pressure trace.** Two features are
measured on the brew plateau, from 1 s after reaching peak until 0.5 s
before pump-off (`classify_profile` in `phase_fit.py`):

- **End ratio:** pressure at the end of the plateau as a fraction of peak.
  Natural decline ends at 72–91% of peak (5th–95th percentile of unflagged
  shots).
- **Plateau RMSE:** how far the plateau departs from a smooth quadratic
  decline. Unflagged shots stay at or below 0.10 bar (95th percentile).

A shot counts as profiled when its end ratio is below 0.65 **or** its RMSE
is above 0.15 bar.

| | detected profiled | detected natural |
|---|---|---|
| **app: Flow Taper** | 24 | 7 |
| **app: not profiled** | 4 | 142 |

The detector agrees with the app flag on 166 of 177 classifiable shots
(94%). The 11 disagreements fall into four groups:

| Shots | What the trace shows |
|---|---|
| 653, 676, 680 (Sara, Oct) | Flagged Flow Taper, but the traces are textbook natural declines. Probably mis-set flags. |
| 328, 332, 398, 428 (Scott, Apr–Jun) | Flagged. Light tapers that only reach about 70% of peak, with small steps. They overlap the natural range, so they can't be separated on these two features. |
| 290, 295 (Apr 21) | Not flagged, but the pressure falls smoothly to 50–60% of peak. Either untagged gentle tapers or fast-eroding pucks. |
| 496, 681 | Not flagged; real modulation. Shot 496's note says the lever was hit by accident mid-shot. Shot 681 dips to about 6 bar and recovers. |

Agreement with the logged extraction time is lower on profiled shots: 64%
within ±3 s, against 84% for natural shots (median logged − fitted +2.1 s
vs +1.0 s). The traces don't show a fitting error. The gap comes from how
the timer was used on those early profiled shots (§5).

![Profile detection](figures/profile_detection.png)

## 7. Decisions (2026-11-01)

1. **Pump-on for Brewmeo auto-start recordings:** estimate it with the
   level calibration (§3), and store an `imputed` flag with the value.
2. **Flow on:** the start of the steady stream from the quadratic curve fit
   (§2), not the first drip.
3. **Truncated recordings:** show pre-infusion and shot time as n/a.
   Profiled shots are a separate case. They get normal estimates; see §6
   and open question A.
4. **Checking entries against telemetry** (e.g. warning when the logged
   extraction time disagrees with the fitted shot time): to be specified
   when the estimator is added to the app.

**Open questions:**

- **A. Display for profiled shots.** Show the fitted times as usual and
  mark the shot as profiled? Is the profile marker taken from the app's
  Flow Taper flag, from the detector, or both?
- **B. The detector and the Flow Taper flag.** Should the detector feed
  back into the flag? For example, it could suggest the flag on upload, or
  report mismatches. This matters because the grind model already excludes
  Flow Taper shots: shots 653, 676 and 680 are probably excluded wrongly,
  and 290 and 295 are probably included wrongly.

## 8. Implementation (v0.11.0)

- `coffee_records/services/telemetry_phases.py` ports `phase_fit.py`. Its
  thresholds are the `telemetry_phases` block of `config.yaml`, and the
  result model is `TelemetryPhases` (`coffee_records/schemas/telemetry.py`).
  Truncated or pressure-less recordings return null times, with the reason
  in `issues`.
- **Brewmeo CSV import** fills Pre-infusion and Extraction time from the
  estimate and appends a "Telemetry estimates (curve fit)" block to the
  notes. When the estimate is n/a, both fields are left empty and a warning
  is shown.
- **`GET /api/shots/<id>/telemetry/phases`** computes the estimate from the
  stored file on request (about 30 ms); nothing new is stored on the shot.
  The telemetry modal shows it under the chart.
- Tests: `test/test_telemetry_phases.py` uses synthetic shots with known
  boundaries (natural, auto-start, truncated, profiled, no pressure).
- Open questions A and B (§7) are still open: the profile detector is shown
  in the modal but doesn't set or check the Flow Taper flag.

## 9. One-time remediation (applied 2026-11-01)

`remediation/proposal.yaml` lists every reviewed change with its reason;
`remediation/apply_remediation.py` applied the approved ones. Each changed
shot got an audit line in its notes, and the previous values were backed up
to a local CSV (not committed).

- **Extraction time corrected on 13 shots:** 289, 330, 363, 405, 431, 465,
  466, 640, 646, 681, 697, 709, 713 (a typo, uncorrected Brewmeo recording
  lengths, and timers started in pre-infusion or at the ramp).
- **Flow Taper cleared on 3 shots:** 653, 676, 680 (natural declines).
- **Declined in review:** 458, 569, 656, 661 (timer started after flow was
  established), plus the low-confidence 606 and Flow Taper on 290, 295, 681.

## Reproducing

Load database credentials with direnv, then run from the repo root:

```bash
poetry run python notebooks/telemetry_phases/explore.py \
    --telemetry-dir /var/www/html/resources/coffee/telemetry
```

The committed `results/` and `figures/` were computed before the §9
remediation, so they compare against the original logged times; re-running
uses the corrected values and shifts the agreement figures slightly.

The script writes `results/phases.csv` (one row per shot, with all
boundaries, profile features and flags), `results/summary.json` and
`figures/*.png`.
