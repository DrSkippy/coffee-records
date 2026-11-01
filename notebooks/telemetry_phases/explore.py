"""Run phase estimation over every shot with telemetry and write the report data.

Usage (from the repo root, with ``.envrc`` loaded for database credentials)::

    poetry run python notebooks/telemetry_phases/explore.py \
        --telemetry-dir /var/www/html/resources/coffee/telemetry

Writes ``results/phases.csv``, ``results/summary.json`` and ``figures/*.png``
next to this file.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_fit as pf  # noqa: E402

HERE = Path(__file__).resolve().parent
logger = logging.getLogger("telemetry_phases")

COLORS = {"beanconqueror": "#228be6", "brewmeo": "#fd7e14"}
MAKER_COLORS = {"Scott": "#228be6", "Sara": "#e64980"}
# Shot time differing from the logged extraction time by more than this is
# listed individually in the report.
DISAGREE_S = 5.0


@dataclass
class ShotRow:
    """Shot record joined to its telemetry file."""

    id: int
    date: str
    maker: str
    pre_infusion_time: str | None
    extraction_time: float | None
    flow_taper: bool
    drink_type: str | None
    telemetry_filename: str


def load_shots() -> list[ShotRow]:
    """Read every shot with telemetry from the application database."""
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ.get('POSTGRES_PORT', '5434')}/{os.environ['POSTGRES_DATABASE']}"
    )
    query = text(
        "select id, date, maker, pre_infusion_time, extraction_time, flow_taper,"
        " drink_type, telemetry_filename from shots"
        " where telemetry_filename is not null order by date, id"
    )
    with create_engine(url).connect() as conn:
        return [
            ShotRow(
                id=r.id,
                date=r.date.isoformat(),
                maker=r.maker,
                pre_infusion_time=r.pre_infusion_time,
                extraction_time=r.extraction_time,
                flow_taper=r.flow_taper,
                drink_type=str(r.drink_type) if r.drink_type else None,
                telemetry_filename=r.telemetry_filename,
            )
            for r in conn.execute(query)
        ]


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _stats(values: list[float]) -> dict[str, float]:
    """Median / quartiles / mean / sd of a sample."""
    if not values:
        return {}
    arr = np.array(values)
    return {
        "n": float(arr.size),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "mean": float(arr.mean()),
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
    }


def calibrate_offsets(
    telemetry: dict[int, pf.Telemetry], results: dict[int, pf.PhaseResult]
) -> dict[str, Any]:
    """Learn how to impute pump-on for recordings that start pressurised.

    Two candidate calibrations, both from recordings that captured the
    pump-on edge:

    * ``level``: time from pump-on until pressure reaches the auto-start
      level (~0.85 bar).
    * ``ramp``: time from pump-on to the main-ramp breakpoint; assumes the
      manual pre-infusion routine is the same length on every shot.
    """
    level_offsets: list[float] = []
    ramp_offsets: list[float] = []
    for shot_id, res in results.items():
        if "pump_on" not in res.fits or res.t_pump_on is None:
            continue
        pressure = telemetry[shot_id].pressure
        reach = pressure.first_crossing(0.85, after=res.t_pump_on)
        if reach is not None:
            level_offsets.append(reach - res.t_pump_on)
        if res.t_ramp is not None:
            ramp_offsets.append(res.t_ramp - res.t_pump_on)
    return {
        "level": _stats(level_offsets),
        "ramp": _stats(ramp_offsets),
        "level_values": level_offsets,
        "ramp_values": ramp_offsets,
    }


def profile_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare telemetry-detected profiling with the app's ``flow_taper`` flag.

    Also reports shot-time agreement with the logged time per group, over
    every shot with a classification (quality flags included).
    """
    classified = [r for r in rows if r["profiled_detected"] != ""]
    confusion = {
        f"app_{flag}_detected_{detected}": [
            r["shot_id"]
            for r in classified
            if r["flow_taper"] is flag and r["profiled_detected"] is detected
        ]
        for flag in (True, False)
        for detected in (True, False)
    }
    agreement: dict[str, Any] = {}
    for detected in (True, False):
        diffs = [
            float(r["logged_extraction_time"]) - float(r["shot_time"])
            for r in classified
            if r["profiled_detected"] is detected
            and r["shot_time"] != ""
            and r["logged_extraction_time"] is not None
        ]
        agreement[f"detected_{detected}"] = {
            "n": len(diffs),
            "median_logged_minus_shot": statistics.median(diffs),
            "within_3s": sum(abs(d) <= 3 for d in diffs) / len(diffs),
        }
    return {
        "n_classified": len(classified),
        "confusion": {k: {"n": len(v), "shots": v} for k, v in confusion.items()},
        "agreement_with_logged": agreement,
    }


def flow_on_sensitivity(
    shots: list[ShotRow], telemetry: dict[int, pf.Telemetry], offset: float
) -> list[dict[str, float]]:
    """Agreement with the logged time across flow-onset model choices.

    Varies the weight-rise segment (line vs quadratic) and the fit window
    (cup weight at which the window ends).
    """
    default_max = pf.FLOW_FIT_MAX_G
    rows: list[dict[str, float]] = []
    try:
        for order in (1, 2):
            for max_g in (2.0, 4.0, 8.0):
                pf.FLOW_FIT_MAX_G = max_g
                diffs: list[float] = []
                pre_infusions: list[float] = []
                for s in shots:
                    res = pf.estimate_phases(
                        telemetry[s.id], pump_on_offset=offset, flow_right_order=order
                    )
                    if res.flags or res.shot_time is None or s.extraction_time is None:
                        continue
                    diffs.append(s.extraction_time - res.shot_time)
                    if not res.pump_on_imputed and res.pre_infusion is not None:
                        pre_infusions.append(res.pre_infusion)
                rows.append(
                    {
                        "right_order": order,
                        "window_max_g": max_g,
                        "n": len(diffs),
                        "median_logged_minus_shot": statistics.median(diffs),
                        "median_abs_diff": statistics.median(map(abs, diffs)),
                        "within_3s": sum(abs(d) <= 3 for d in diffs) / len(diffs),
                        "median_pre_infusion_measured": statistics.median(
                            pre_infusions
                        ),
                    }
                )
    finally:
        pf.FLOW_FIT_MAX_G = default_max
    return rows


def plot_fits(axis: Axes, row: ShotRow, tel: pf.Telemetry, res: pf.PhaseResult) -> None:
    """Draw one shot's signals, fitted segments and phase boundaries."""
    weight_axis = axis.twinx()
    axis.plot(tel.pressure.t, tel.pressure.y, color="#fd7e14", lw=1)
    weight_axis.plot(tel.weight.t, tel.weight.y, color="#228be6", lw=1)
    for name, fit in res.fits.items():
        tt = np.linspace(fit.t0 - 3, fit.t0 + 3, 60)
        target = weight_axis if name == "flow_on" else axis
        target.plot(tt, fit.predict(tt), "k--", lw=0.9)
    marks = [
        (res.t_pump_on, "#e03131", "pump on"),
        (res.t_ramp, "#ae3ec9", "ramp"),
        (res.t_flow_on, "#1971c2", "flow on"),
        (res.t_pump_off, "#212529", "pump off"),
    ]
    for value, color, _ in marks:
        if value is not None:
            axis.axvline(
                value, color=color, lw=0.9, ls=":" if color == "#ae3ec9" else "-"
            )
    axis.set_ylim(-0.5, 10)
    weight_axis.set_ylim(-2, 50)
    pi, shot = res.pre_infusion, res.shot_time
    axis.set_title(
        f"#{row.id} {row.date} {row.maker} ({tel.source})\n"
        f"pre-inf {'n/a' if pi is None else f'{pi:.1f}'} s"
        f"{'*' if res.pump_on_imputed else ''}, "
        f"shot {'n/a' if shot is None else f'{shot:.1f}'} s "
        f"(logged {row.extraction_time})",
        fontsize=8,
    )
    axis.tick_params(labelsize=7)
    weight_axis.tick_params(labelsize=7)


def main() -> None:
    """Fit every shot, then write CSV, summary and figures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--telemetry-dir",
        type=Path,
        default=Path("/var/www/html/resources/coffee/telemetry"),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "figures").mkdir(exist_ok=True)

    shots = load_shots()
    telemetry = {
        s.id: pf.load_telemetry(args.telemetry_dir / s.telemetry_filename)
        for s in shots
    }
    logger.info("Loaded %d shots with telemetry", len(shots))

    # Pass 1: un-imputed fits, used to calibrate the pump-on imputation.
    first = {sid: pf.estimate_phases(tel) for sid, tel in telemetry.items()}
    calib = calibrate_offsets(telemetry, first)
    level_offset = calib["level"]["median"]
    ramp_offset = calib["ramp"]["median"]

    # Pass 2: impute pump-on for pressurised starts (level calibration), and
    # also record the ramp-aligned alternative.
    results: dict[int, pf.PhaseResult] = {}
    rows_out: list[dict[str, Any]] = []
    for s in shots:
        tel = telemetry[s.id]
        res = pf.estimate_phases(tel, pump_on_offset=level_offset)
        linear = pf.fit_flow_on(
            pf.Signal(tel.weight.t, pf.median_filter(tel.weight.y)),
            res.t_pump_on or 0.0,
            right_order=1,
        )
        results[s.id] = res
        pi_ramp = (
            None
            if res.t_flow_on is None or res.t_ramp is None
            else (
                res.pre_infusion
                if "pump_on" in res.fits
                else res.t_flow_on - res.t_ramp + ramp_offset
            )
        )
        rows_out.append(
            {
                "shot_id": s.id,
                "date": s.date,
                "maker": s.maker,
                "source": tel.source,
                "drink_type": s.drink_type,
                "flow_taper": s.flow_taper,
                "logged_pre_infusion": s.pre_infusion_time,
                "logged_extraction_time": s.extraction_time,
                "t_pump_on": _fmt(res.t_pump_on),
                "pump_on_imputed": res.pump_on_imputed,
                "t_ramp": _fmt(res.t_ramp),
                "t_flow_on": _fmt(res.t_flow_on),
                "t_flow_on_linear": _fmt(linear.t0 if linear else None),
                "t_pump_off": _fmt(res.t_pump_off),
                "pre_infusion": _fmt(res.pre_infusion),
                "pre_infusion_ramp_aligned": _fmt(pi_ramp),
                "shot_time": _fmt(res.shot_time),
                "total_time": _fmt(
                    None
                    if res.t_pump_on is None or res.t_pump_off is None
                    else res.t_pump_off - res.t_pump_on
                ),
                "flow_on_rmse_g": _fmt(
                    res.fits["flow_on"].rmse if "flow_on" in res.fits else None
                ),
                "pump_off_rmse_bar": _fmt(
                    res.fits["pump_off"].rmse if "pump_off" in res.fits else None
                ),
                "end_ratio": _fmt(res.end_ratio),
                "plateau_rmse_bar": _fmt(res.plateau_rmse),
                "profiled_detected": "" if res.profiled is None else res.profiled,
                "flags": ";".join(res.flags),
            }
        )

    with (HERE / "results" / "phases.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)

    # ---- Summary statistics ------------------------------------------------
    def num(row: dict[str, Any], key: str) -> float | None:
        value = row[key]
        return float(value) if value not in ("", None) else None

    ok = [r for r in rows_out if not r["flags"]]
    summary: dict[str, Any] = {
        "n_shots": len(rows_out),
        "by_source": {
            src: sum(1 for r in rows_out if r["source"] == src)
            for src in ("beanconqueror", "brewmeo")
        },
        "flags": {},
        "calibration": {k: calib[k] for k in ("level", "ramp")},
    }
    for r in rows_out:
        for flag in filter(None, r["flags"].split(";")):
            summary["flags"].setdefault(flag, []).append(r["shot_id"])
    imputed_ids = {r["shot_id"] for r in ok if r["pump_on_imputed"]}
    measured = [r for r in ok if not r["pump_on_imputed"]]
    summary["n_pump_on_measured"] = len(measured)
    summary["n_pump_on_imputed"] = len(imputed_ids)

    def collect(rows: list[dict[str, Any]], key: str) -> list[float]:
        return [v for r in rows if (v := num(r, key)) is not None]

    summary["pre_infusion_measured"] = _stats(collect(measured, "pre_infusion"))
    summary["pre_infusion_imputed_level"] = _stats(
        collect([r for r in ok if r["pump_on_imputed"]], "pre_infusion")
    )
    summary["pre_infusion_imputed_ramp"] = _stats(
        collect([r for r in ok if r["pump_on_imputed"]], "pre_infusion_ramp_aligned")
    )
    summary["flow_on_minus_ramp"] = _stats(
        [
            f - rp
            for r in ok
            if (f := num(r, "t_flow_on")) is not None
            and (rp := num(r, "t_ramp")) is not None
        ]
    )
    summary["shot_time"] = _stats(collect(ok, "shot_time"))
    summary["flow_on_quadratic_minus_linear"] = _stats(
        [
            q - lin
            for r in ok
            if (q := num(r, "t_flow_on")) is not None
            and (lin := num(r, "t_flow_on_linear")) is not None
        ]
    )
    summary["flow_on_sensitivity"] = flow_on_sensitivity(shots, telemetry, level_offset)

    agreement: dict[str, Any] = {}
    for maker in ("Scott", "Sara"):
        pairs = [
            (st, lg, tot)
            for r in ok
            if r["maker"] == maker
            and (st := num(r, "shot_time")) is not None
            and (lg := num(r, "logged_extraction_time")) is not None
            and (tot := num(r, "total_time")) is not None
        ]
        d_shot = [lg - st for st, lg, _ in pairs]
        d_total = [lg - tot for _, lg, tot in pairs]
        agreement[maker] = {
            "n": len(pairs),
            "logged_minus_shot_time": _stats(d_shot),
            "logged_minus_total_time": _stats(d_total),
            "median_abs_logged_minus_shot": (
                statistics.median(map(abs, d_shot)) if d_shot else None
            ),
            "median_abs_logged_minus_total": (
                statistics.median(map(abs, d_total)) if d_total else None
            ),
        }
    summary["agreement_with_logged"] = agreement
    summary["disagreements"] = [
        {
            "shot_id": r["shot_id"],
            "date": r["date"],
            "maker": r["maker"],
            "logged": num(r, "logged_extraction_time"),
            "shot_time": num(r, "shot_time"),
            "total_time": num(r, "total_time"),
        }
        for r in ok
        if r["maker"] == "Scott"
        and (st := num(r, "shot_time")) is not None
        and (lg := num(r, "logged_extraction_time")) is not None
        and abs(lg - st) > DISAGREE_S
    ]
    summary["profile"] = profile_summary(rows_out)
    (HERE / "results" / "summary.json").write_text(
        json.dumps(summary, indent=2, default=float)
    )
    logger.info("Summary:\n%s", json.dumps(summary, indent=2, default=float))

    # ---- Figures -----------------------------------------------------------
    by_id = {s.id: s for s in shots}
    sample_ids = [shots[i].id for i in np.linspace(0, len(shots) - 1, 12).astype(int)]
    fig = Figure(figsize=(18, 13))
    for i, sid in enumerate(sample_ids):
        plot_fits(
            fig.add_subplot(3, 4, i + 1), by_id[sid], telemetry[sid], results[sid]
        )
    fig.suptitle(
        "Fitted segments (dashed) and phase boundaries: red pump on, purple "
        "ramp, blue flow on, black pump off. * = pump-on imputed",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "fit_examples.png", dpi=80)

    flagged = [sid for ids in summary["flags"].values() for sid in ids][:8]
    worst = sorted(
        summary["disagreements"],
        key=lambda d: -abs((d["logged"] or 0) - (d["shot_time"] or 0)),
    )
    trouble = list(dict.fromkeys(flagged + [d["shot_id"] for d in worst]))[:8]
    if trouble:
        fig = Figure(figsize=(18, 9))
        for i, sid in enumerate(trouble):
            plot_fits(
                fig.add_subplot(2, 4, i + 1), by_id[sid], telemetry[sid], results[sid]
            )
        fig.suptitle(
            "Flagged shots and largest disagreements with the logged time", fontsize=10
        )
        fig.tight_layout()
        fig.savefig(HERE / "figures" / "problem_shots.png", dpi=80)

    fig = Figure(figsize=(14, 4.5))
    ax1, ax2, ax3 = (fig.add_subplot(1, 3, i) for i in (1, 2, 3))
    bins = np.arange(0, 30, 0.5).tolist()
    ax1.hist(
        collect(measured, "pre_infusion"),
        bins=bins,
        color=COLORS["beanconqueror"],
        alpha=0.7,
        label="pump-on measured",
    )
    ax1.hist(
        collect([r for r in ok if r["pump_on_imputed"]], "pre_infusion"),
        bins=bins,
        color=COLORS["brewmeo"],
        alpha=0.6,
        label="pump-on imputed (level)",
    )
    ax1.set(title="Pre-infusion (pump on → flow on)", xlabel="s", ylabel="shots")
    ax1.legend(fontsize=8)
    ax2.hist(
        collect(ok, "shot_time"), bins=np.arange(10, 60, 1).tolist(), color="#495057"
    )
    ax2.set(title="Shot time (flow on → pump off)", xlabel="s")
    ax3.hist(
        calib["ramp_values"],
        bins=np.arange(0, 15, 0.5).tolist(),
        color="#ae3ec9",
        alpha=0.7,
        label="pump on → ramp",
    )
    ax3.hist(
        [
            f - rp
            for r in ok
            if (f := num(r, "t_flow_on")) is not None
            and (rp := num(r, "t_ramp")) is not None
        ],
        bins=np.arange(-2, 15, 0.5).tolist(),
        color="#1971c2",
        alpha=0.6,
        label="ramp → flow on",
    )
    ax3.set(title="Pre-infusion components", xlabel="s")
    ax3.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "distributions.png", dpi=90)

    fig = Figure(figsize=(12, 5))
    ax1, ax2 = fig.add_subplot(1, 2, 1), fig.add_subplot(1, 2, 2)
    for maker, color in MAKER_COLORS.items():
        pts = [
            (st, lg, tot)
            for r in ok
            if r["maker"] == maker
            and (st := num(r, "shot_time")) is not None
            and (lg := num(r, "logged_extraction_time")) is not None
            and (tot := num(r, "total_time")) is not None
            and lg < 90
        ]
        if not pts:
            continue
        shot_times, logged, totals = zip(*pts)
        ax1.scatter(shot_times, logged, s=14, color=color, label=maker, alpha=0.7)
        ax2.scatter(totals, logged, s=14, color=color, label=maker, alpha=0.7)
    for ax, xlabel in (
        (ax1, "fitted shot time (flow on → pump off), s"),
        (ax2, "fitted total time (pump on → pump off), s"),
    ):
        ax.plot([10, 80], [10, 80], color="#adb5bd", lw=1)
        ax.set(
            xlabel=xlabel,
            ylabel="logged extraction time, s",
            xlim=(10, 80),
            ylim=(10, 80),
        )
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    ax1.set_title("Logged vs fitted shot time")
    ax2.set_title("Logged vs fitted total time")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "logged_vs_fitted.png", dpi=90)

    fig = Figure(figsize=(12, 4))
    ax = fig.add_subplot()
    dates = np.array(
        [np.datetime64(r["date"]) for r in ok if num(r, "pre_infusion") is not None]
    )
    vals = np.array(collect(ok, "pre_infusion"))
    imputed = np.array(
        [r["pump_on_imputed"] for r in ok if num(r, "pre_infusion") is not None]
    )
    ax.scatter(
        dates[~imputed],
        vals[~imputed],
        s=12,
        color=COLORS["beanconqueror"],
        label="pump-on measured",
    )
    ax.scatter(
        dates[imputed],
        vals[imputed],
        s=12,
        color=COLORS["brewmeo"],
        label="pump-on imputed",
    )
    ax.set(title="Fitted pre-infusion over time", ylabel="s")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "pre_infusion_over_time.png", dpi=90)

    fig = Figure(figsize=(7, 5))
    ax = fig.add_subplot()
    for flag, color, label in (
        (False, "#228be6", "app: not profiled"),
        (True, "#e8590c", "app: Flow Taper"),
    ):
        ratio_rmse = [
            (float(r["end_ratio"]), float(r["plateau_rmse_bar"]))
            for r in rows_out
            if r["end_ratio"] != "" and r["flow_taper"] is flag
        ]
        xs, ys = zip(*ratio_rmse)
        ax.scatter(xs, ys, s=16, color=color, alpha=0.75, label=label)
    for r in rows_out:
        if r["end_ratio"] != "" and r["flow_taper"] is not r["profiled_detected"]:
            ax.annotate(
                str(r["shot_id"]),
                (float(r["end_ratio"]), float(r["plateau_rmse_bar"])),
                fontsize=7,
                xytext=(3, 3),
                textcoords="offset points",
            )
    ax.axvline(pf.PROFILE_END_RATIO, color="#868e96", lw=1, ls="--")
    ax.axhline(pf.PROFILE_RMSE_BAR, color="#868e96", lw=1, ls="--")
    ax.set_yscale("log")
    ax.set(
        title="Profile detection: profiled = left of or above the dashed lines",
        xlabel="plateau-end pressure / peak pressure",
        ylabel="plateau deviation from smooth decline (RMSE, bar)",
    )
    ax.title.set_fontsize(9)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "profile_detection.png", dpi=90)
    logger.info("Wrote results and figures under %s", HERE)


if __name__ == "__main__":
    main()
