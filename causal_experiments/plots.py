"""Legible figures at the paper's final width, using measured CSV outputs."""
from __future__ import annotations
from pathlib import Path
from fractions import Fraction
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, NullFormatter
import numpy as np
import pandas as pd
from .experiments import STAGES

PAPER_WIDTH_IN = 6.75
COMPACT_HEIGHT_IN = 2.1
PAPER_STYLE = {
    "figure.dpi": 120, "savefig.dpi": 300, "font.size": 11,
    "axes.labelsize": 11, "axes.titlesize": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .8, "pdf.fonttype": 42, "svg.fonttype": "none",
}
COLORS = {0.0: "#285D8E", 0.25: "#C36B10", 0.5: "#28734C"}
MARKERS = {0.0: "o", 0.25: "s", 0.5: "^"}


def _save_figure(fig, out, name):
    folder = Path(out) / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    # Fixed canvas avoids changing the height when placed at full paper width.
    for extension in ["png", "svg", "pdf"]:
        fig.savefig(folder / f"{name}.{extension}", facecolor="white")


def _comparison_axes(modules, ylabel):
    fig, axes = plt.subplots(1, len(modules), figsize=(PAPER_WIDTH_IN, COMPACT_HEIGHT_IN),
                             sharex=True, sharey=True, squeeze=False)
    # Keep a compact, separate legend row and use the remaining canvas for plots.
    fig.subplots_adjust(left=.12, right=.99, bottom=.33, top=.985, wspace=.10)
    for ax, count in zip(axes[0], modules):
        ax.set(xscale="log", yscale="log")
        # The empty upper-left corner can hold the panel label without
        # consuming a separate title row above the plotting area.
        ax.text(.04, .95, f"{count} modules", transform=ax.transAxes,
                ha="left", va="top", fontsize=11)
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.xaxis.set_major_locator(LogLocator(base=10, numticks=6))
        ax.yaxis.set_major_locator(LogLocator(base=10, numticks=5))
        ax.tick_params(axis="both", which="major", pad=2, length=3)
        ax.grid(alpha=.18, linewidth=.6)
    axes[0, 0].set_ylabel(ylabel, labelpad=2)
    fig.supxlabel(r"Supplied input size $N+R$", x=.555, y=.135, fontsize=11)
    return fig, axes[0]


def _copy_legend(fig, ax):
    # Fit the left margin to the actual y-label width, leaving four points
    # of outer padding and giving the recovered space to all three panels.
    fig.canvas.draw()
    label_box = ax.yaxis.label.get_window_extent(fig.canvas.get_renderer())
    padding_px = 4 * fig.dpi / 72
    left = fig.subplotpars.left + (padding_px - label_box.x0) / fig.bbox.width
    fig.subplots_adjust(left=left)
    center = (left + fig.subplotpars.right) / 2
    fig._supxlabel.set_x(center)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(center, .02),
               ncol=len(labels), frameon=False, handlelength=1.6, handletextpad=.45,
               columnspacing=1.3, borderaxespad=.25, borderpad=0)


def plot_scaling(out):
    out = Path(out)
    timings = pd.read_csv(out / "timings.csv")
    summary = pd.read_csv(out / "timing_summary.csv")
    memory = pd.read_csv(out / "memory.csv") if (out / "memory.csv").exists() else pd.DataFrame()
    modules = sorted(timings.modules.unique())
    copies = sorted(timings.copy_fraction.unique())
    figures = []
    with plt.rc_context(PAPER_STYLE):
        fig, axes = _comparison_axes(modules, "Structural time (s)")
        for ax, count in zip(axes, modules):
            for fraction in copies:
                rows = summary[(summary.modules == count) & (summary.copy_fraction == fraction)].sort_values("median_N_plus_R")
                ax.errorbar(rows.median_N_plus_R, rows.median_s,
                            yerr=np.vstack([rows.median_s - rows.q25_s, rows.q75_s - rows.median_s]),
                            marker=MARKERS[fraction], markersize=4.5, linewidth=1.5,
                            elinewidth=1, capsize=2.5, color=COLORS[fraction], label=f"{fraction:.0%} copies")
        axes[0].set_xlim(summary.median_N_plus_R.min() * .75, summary.median_N_plus_R.max() * 1.3)
        _copy_legend(fig, axes[0])
        _save_figure(fig, out, "runtime")
        figures.append(fig)

        largest = int(timings.n_endogenous.max())
        breakdown = timings[timings.n_endogenous == largest].groupby(["modules", "copy_fraction"])[STAGES].median()
        stage_names = ["Input checks", "Join records", "Remove duplicates", "Global tables", "Global checks"]
        stage_colors = ["#285D8E", "#4199B4", "#ECC05B", "#C36B10", "#28734C"]
        fig, panels = plt.subplots(1, len(modules), figsize=(PAPER_WIDTH_IN, 2.7), sharey=True, squeeze=False)
        fig.subplots_adjust(left=.105, right=.99, bottom=.22, top=.67, wspace=.15)
        for ax, count in zip(panels[0], modules):
            positions = np.arange(len(copies))
            bottom = np.zeros(len(copies))
            for stage, label, color in zip(STAGES, stage_names, stage_colors):
                heights = np.array([breakdown.loc[(count, fraction), stage] for fraction in copies])
                ax.bar(positions, heights, bottom=bottom, label=label, color=color, width=.65)
                bottom += heights
            ax.set_title(f"{count} modules")
            ax.set_xticks(positions, [f"{fraction:.0%}" for fraction in copies])
            ax.grid(axis="y", alpha=.18, linewidth=.6)
            ax.set_axisbelow(True)
        panels[0, 0].set_ylabel("Median stage time (s)")
        handles, labels = panels[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.55, 1.0),
                   ncol=3, frameon=False, handlelength=1, handletextpad=.4, columnspacing=1.0)
        fig.supxlabel(f"Copied mechanisms (n={largest:,})", y=.015, fontsize=11)
        _save_figure(fig, out, "stage_breakdown")
        figures.append(fig)

        if not memory.empty:
            fig, axes = _comparison_axes(modules, "Peak allocation\n(MiB)")
            measured = memory.assign(N_plus_R=memory.N + memory.R, peak_MiB=memory.peak_python_bytes / 2**20)
            for ax, count in zip(axes, modules):
                for fraction in copies:
                    rows = measured[(measured.modules == count) & (measured.copy_fraction == fraction)]
                    grouped = rows.groupby("n_endogenous").agg(
                        scale=("N_plus_R", "median"), peak=("peak_MiB", "median"),
                        low=("peak_MiB", "min"), high=("peak_MiB", "max")).sort_values("scale")
                    ax.errorbar(grouped.scale, grouped.peak,
                                yerr=np.vstack([grouped.peak - grouped.low, grouped.high - grouped.peak]),
                                marker=MARKERS[fraction], markersize=4.5, linewidth=1.5,
                                elinewidth=1, capsize=2.5, color=COLORS[fraction], label=f"{fraction:.0%} copies")
            axes[0].set_xlim(measured.N_plus_R.min() * .75, measured.N_plus_R.max() * 1.3)
            _copy_legend(fig, axes[0])
            _save_figure(fig, out, "memory")
            figures.append(fig)
    return figures


def plot_running_example(out):
    out = Path(out)
    responses = pd.read_csv(out / "running_example_response.csv").to_dict("records")
    saved = pd.read_csv(out / "running_example_values.csv").set_index("context")
    with plt.rc_context(PAPER_STYLE):
        fig = plt.figure(figsize=(PAPER_WIDTH_IN, 4.3))
        grid = fig.add_gridspec(2, 2, height_ratios=[1.35, 1], left=.12, right=.97,
                               bottom=.12, top=.93, hspace=.75, wspace=.20)
        diagrams = [fig.add_subplot(grid[0, i]) for i in range(2)]
        response = fig.add_subplot(grid[1, :])
        positions = {"UX": (0, 1.5), "X": (0, .5), "UY": (1.25, 1.5), "Y": (1.25, .5),
                     "Y_boundary": (2.5, .5), "UZ": (3.75, 1.5), "Z": (3.75, .5)}
        for ax, context, intervened in zip(diagrams, ["observational", "do_Y_0"], [False, True]):
            values = saved.loc[context].to_dict()
            ax.set(xlim=(-.55, 4.30), ylim=(-.45, 2)); ax.axis("off")
            edges = [("UX", "X"), ("X", "Y"), ("UY", "Y"), ("Y", "Y_boundary"),
                     ("Y_boundary", "Z"), ("UZ", "Z")]
            for a, b in edges:
                if intervened and b == "Y": continue
                ax.annotate("", xy=positions[b], xytext=positions[a],
                            arrowprops={"arrowstyle": "->", "color": "#556575", "linewidth": 1.4,
                                        "shrinkA": 15, "shrinkB": 15,
                                        "linestyle": "--" if b == "Y_boundary" else "-"})
            for name, (x, y) in positions.items():
                boundary = name == "Y_boundary"
                label = f"Y'={int(values['Y'])}" if boundary else f"{name}={int(values[name])}"
                ax.text(x, y, label, ha="center", va="center", fontsize=11,
                        bbox={"boxstyle": "round,pad=.25", "facecolor": "white" if boundary else
                              ("#F1F3F5" if name in {"UX", "UY", "UZ"} else "#E6EEF7"), "edgecolor": "#285D8E"})
            ax.text(2.5, .0, "boundary", ha="center", color="#285D8E", fontsize=10)
            equation = "X=UX; Y=X XOR UY" if not intervened else "X=UX; do(Y=0)"
            ax.text(.5, -.03, equation, ha="center", transform=ax.transAxes, fontsize=10)
            ax.text(.5, -.21, "Z=Y' XOR UZ", ha="center", transform=ax.transAxes, fontsize=10)
            ax.set_title("Observed values" if not intervened else "After do(Y=0)", fontsize=12)
        response.bar(["do(Y=0)", "do(Y=1)"], [float(Fraction(row["P_Z_1_exact"])) for row in responses],
                     color=["#285D8E", "#C36B10"], width=.5)
        response.set(ylim=(0, 1), ylabel="P(Z=1)", title="Exact response with P(UZ=1)=1/5")
        response.grid(axis="y", alpha=.18, linewidth=.6); response.set_axisbelow(True)
        for index, row in enumerate(responses):
            response.text(index, float(Fraction(row["P_Z_1_exact"])) + .035,
                          row["P_Z_1_exact"], ha="center", fontsize=12)
        _save_figure(fig, out, "running_example")
    return fig
