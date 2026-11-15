"""Builds the written report (output/SEIR_Report.pdf, 5-8 pages) from the
pipeline artifacts and the text content in report_text.py.

Layout: fpdf2, A4, Helvetica core fonts (Latin-1; all text is ASCII-safe).
Figures are placed with runtime aspect-ratio handling (PIL) and capped
heights so the document reliably fits the 5-8 page requirement.

Usage:  python make_report.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from fpdf import FPDF
from fpdf.fonts import FontFace
from PIL import Image
from pypdf import PdfReader

import config as cfg
import report_text as rt

PLOTS_DIR = cfg.PLOTS_DIR
METRICS_PATH = cfg.METRICS_JSON
DATASET_META_PATH = cfg.DATASET_METADATA_JSON
DATASET_CSV_PATH = cfg.DATASET_CSV
REPORT_PATH = cfg.OUTPUT_DIR / "SEIR_Report.pdf"

PAGE_W, PAGE_H = 210, 297  # A4 mm
MARGIN = 18
CONTENT_W = PAGE_W - 2 * MARGIN

NAVY = (22, 40, 60)
ACCENT = (0, 114, 178)
GRAY = (100, 110, 120)
LIGHT = (240, 244, 248)

# Figure sizing (mm)
FIG_W_SINGLE = 108
FIG_H_SINGLE_MAX = 72
FIG_W_PAIR = 82
FIG_H_PAIR_MAX = 56

SCENARIO_LABELS = {
    "baseline": "Baseline (no action)",
    "lockdown": "Lockdown (days 40-99)",
    "masking": "Sustained masking",
    "vaccination_only": "Vaccination only",
    "combined": "Combined strategy",
}

REPLACEMENTS = {
    "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2248": "approx. ", "\u00d7": "x",
    "\u2192": "->", "\u2265": ">=", "\u2264": "<=",
}


def sanitize(text: str) -> str:
    """Map the few non-Latin-1 characters to ASCII equivalents."""
    for src, dst in REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text


def trailing_zero_days() -> int:
    """Length of the consecutive zero-reported-case run ending the dataset."""
    series = pd.read_csv(DATASET_CSV_PATH)["reported_new_cases"].to_numpy()
    count = 0
    for value in reversed(series):
        if value == 0:
            count += 1
        else:
            break
    return count


def load_values() -> dict:
    """Map pipeline artifacts (metrics.json, dataset_metadata.json) to the
    named placeholders used in report_text.py. Shared with make_pptx.py."""
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    meta = json.loads(DATASET_META_PATH.read_text(encoding="utf-8"))
    true_params = meta.get("true_parameters", {})
    study = metrics["study"]
    cal = metrics["calibration"]["fitted_parameters"]
    diag = metrics["calibration"]["diagnostics"]
    sc = metrics["scenarios"]
    ds = metrics["dataset"]

    gamma = study["gamma"]
    base, lock, mask, vacc, comb = (
        sc["baseline"], sc["lockdown"], sc["masking"],
        sc["vaccination_only"], sc["combined"],
    )
    beta0_true = true_params["beta0"]
    rho_true = true_params["reporting_fraction"]

    # Nominal transmission multipliers straight from the scenario definitions,
    # so the reported R_eff figures can never drift from the configuration.
    multipliers = {
        (scenario.name, day): multiplier
        for scenario in cfg.SCENARIO_DEFINITIONS
        for day, multiplier in scenario.beta_segments
    }
    r0_fit = cal["beta0"] / gamma

    values = {
        "population": study["population"],
        "capacity": study["healthcare_capacity"],
        "days": study["days"],
        # dataset / ground truth
        "beta0_true": beta0_true,
        "rho_true": rho_true,
        "r0_true": beta0_true / gamma,
        "observed_peak_day": ds["observed_peak_day"],
        "zero_days": ds["days_with_zero_reported_cases"],
        "trailing_zero_days": trailing_zero_days(),
        "total_reported": ds["cumulative_reported_cases"],
        # calibration
        "beta0_fit": cal["beta0"],
        "rho_fit": cal["rho"],
        "r0_fit": r0_fit,
        "lockdown_reff": r0_fit * multipliers[("lockdown", 40)],
        "masking_reff": r0_fit * multipliers[("masking", 30)],
        "relaxed_reff": r0_fit * multipliers[("lockdown", 100)],
        "combined_reff": r0_fit * multipliers[("combined", 40)],
        "combined_relax_reff": r0_fit * multipliers[("combined", 100)],
        "r_squared": diag["r_squared"],
        "rmse": diag["rmse"],
        "mae": diag["mae"],
        # scenarios
        "base_peak": base["peak_infectious"],
        "base_peak_day": base["peak_day"],
        "base_total_pct": base["attack_rate_percent"],
        "base_overload_days": base["days_above_capacity"],
        "lockdown_peak_red": lock["reduction_peak_infectious_percent"],
        "lockdown_overload_days": lock["days_above_capacity"],
        "masking_peak_red": mask["reduction_peak_infectious_percent"],
        "masking_overload_days": mask["days_above_capacity"],
        "vacc_total_red": vacc["reduction_total_infections_percent"],
        "combined_peak": comb["peak_infectious"],
        "combined_total_pct": comb["attack_rate_percent"],
        "combined_total_red": comb["reduction_total_infections_percent"],
        "combined_overload_days": comb["days_above_capacity"],
        # derived text
        "attack_rate_span_text": (
            f"{comb['attack_rate_percent']:.1f}% (combined) to "
            f"{base['attack_rate_percent']:.1f}% (baseline)"
        ),
    }
    return values


def scenario_rows(metrics: dict) -> tuple[list[str], list[list[str]]]:
    """(headers, rows) for the scenario comparison table."""
    sc = metrics["scenarios"]
    order = ["baseline", "lockdown", "masking", "vaccination_only", "combined"]
    headers = ["Scenario", "Peak infectious", "Peak day", "Total infections",
               "Attack rate", "Days > capacity", "Peak reduction"]
    rows = []
    for name in order:
        m = sc[name]
        peak_red = m["reduction_peak_infectious_percent"]
        rows.append([
            SCENARIO_LABELS[name],
            f"{m['peak_infectious']:,.0f}",
            f"{m['peak_day']}",
            f"{m['total_infections']:,.0f}",
            f"{m['attack_rate_percent']:.1f}%",
            f"{m['days_above_capacity']}",
            "-" if peak_red is None else f"-{peak_red:.1f}%",
        ])
    return headers, rows


def dataset_rows(metrics: dict, meta: dict) -> tuple[list[str], list[list[str]]]:
    ds = metrics["dataset"]
    study = metrics["study"]
    true_params = meta.get("true_parameters", {})
    headers = ["Property", "Value"]
    rows = [
        ["Population (city)", f"{study['population']:,}"],
        ["Horizon", f"{study['days']} days (daily resolution)"],
        ["True transmission beta0 / R0",
         f"{true_params['beta0']:.2f} / {true_params['beta0'] / study['gamma']:.2f}"],
        ["Ascertainment fraction (true)", f"rho = {true_params['reporting_fraction']:.2f}"],
        ["Total reported cases", f"{ds['cumulative_reported_cases']:,}"],
        ["Peak daily reported cases",
         f"{ds['observed_peak_reported_cases']:,} on day {ds['observed_peak_day']}"],
        ["Mean daily reported cases", f"{ds['mean_daily_reported_cases']:.1f}"],
        ["Total vaccinations administered", f"{ds['total_vaccinations']:,}"],
        ["Days with zero reported cases (total)", f"{ds['days_with_zero_reported_cases']}"],
        ["Consecutive zero-case days at horizon end", f"{trailing_zero_days()}"],
    ]
    return headers, rows


class ReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(MARGIN, 16, MARGIN)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(rt.REPORT_TITLE)
        self.set_author(", ".join(rt.MEMBERS[:2]) + " et al. (Group 1, Section 2)")
        self.alias_nb_pages()

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.cell(90, 5, "SEIR Epidemic Simulation - Group 1, Section 2", align="L")
        self.cell(0, 5, "Computational Science", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")

    # ---------------------------------------------------------------- blocks
    def title_page(self) -> None:
        self.add_page()
        self.ln(48)
        self.set_font("Helvetica", "B", 25)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 11, rt.REPORT_TITLE, align="C")
        self.ln(3)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.8)
        self.line(70, self.get_y(), 140, self.get_y())
        self.ln(8)
        self.set_font("Helvetica", "", 13.5)
        self.set_text_color(60, 70, 80)
        self.multi_cell(0, 7, rt.REPORT_SUBTITLE, align="C")
        self.ln(14)
        self.set_font("Helvetica", "", 11.5)
        self.set_text_color(40, 48, 56)
        self.multi_cell(0, 6.5, rt.COURSE + "\n" + rt.GROUP, align="C")
        self.ln(12)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, "Group Members", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font("Helvetica", "", 10.5)
        for member in rt.MEMBERS:
            self.set_text_color(60, 68, 76)
            self.cell(0, 5.6, member, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(16)
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(*GRAY)
        self.multi_cell(0, 5.5,
                        "A computational study combining synthetic data generation, ODE-based "
                        "epidemic modeling, least-squares calibration, and policy scenario analysis.\n"
                        "November 2026", align="C")

    def h1(self, text: str) -> None:
        self.ln(1.5)
        self.set_font("Helvetica", "B", 13.5)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 7, sanitize(text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.5)
        self.line(MARGIN, self.get_y() + 0.5, MARGIN + 42, self.get_y() + 0.5)
        self.ln(3.5)

    def para(self, text: str, size: float = 10.2, lh: float = 5.15) -> None:
        self.set_font("Helvetica", "", size)
        self.set_text_color(35, 40, 46)
        self.multi_cell(0, lh, sanitize(text), align="J")
        self.ln(2.2)

    def bullets(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 10.2)
        self.set_text_color(35, 40, 46)
        for item in items:
            y0 = self.get_y()
            self.set_x(MARGIN + 2)
            self.cell(5, 5.15, "-")
            self.multi_cell(CONTENT_W - 9, 5.15, sanitize(item), align="J")
            self.set_x(MARGIN + 2)
            self.ln(1.6)
        self.ln(1.2)

    def equations(self, lines: list[str]) -> None:
        block_h = 5.4 * len(lines) + 9.0
        if self.get_y() + block_h > self.page_break_trigger:
            self.add_page()
        self.set_fill_color(*LIGHT)
        self.set_draw_color(205, 214, 222)
        self.set_line_width(0.2)
        self.set_font("Courier", "", 9.5)
        self.set_text_color(30, 40, 55)
        x0, y0 = MARGIN + 8, self.get_y() + 1.5
        self.rect(x0 - 3, y0 - 1.5, CONTENT_W - 12, 5.4 * len(lines) + 4, "DF")
        self.set_xy(x0, y0)
        for line in lines:
            self.cell(0, 5.4, "  " + sanitize(line), new_x="LMARGIN", new_y="NEXT")
        self.ln(3.5)

    def refs(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 9.3)
        self.set_text_color(35, 40, 46)
        for item in items:
            self.multi_cell(0, 4.7, sanitize(item), align="J")
            self.ln(1.8)

    # -------------------------------------------------------------- figures
    def _fit_size(self, path: Path, width: float, max_h: float) -> tuple[float, float]:
        with Image.open(path) as im:
            w_px, h_px = im.size
        aspect = h_px / w_px
        h = width * aspect
        if h > max_h:
            h = max_h
            width = h / aspect
        return width, h

    def figure(self, filename: str, caption: str, width: float = FIG_W_SINGLE,
               max_h: float = FIG_H_SINGLE_MAX) -> None:
        path = PLOTS_DIR / filename
        w_mm, h_mm = self._fit_size(path, width, max_h)
        top = self.get_y()
        if top + h_mm + 14 > self.page_break_trigger:
            self.add_page()
            top = self.get_y()
        self.image(str(path), x=(PAGE_W - w_mm) / 2, y=top, w=w_mm)
        self.set_y(top + h_mm + 1.8)
        self.set_font("Helvetica", "I", 8.6)
        self.set_text_color(*GRAY)
        self.multi_cell(0, 4.1, sanitize(caption), align="C")
        self.ln(2.6)

    def figure_pair(self, items: list[tuple[str, str]]) -> None:
        fitted = []
        for name, _caption in items:
            path = PLOTS_DIR / name
            w_mm, h_mm = self._fit_size(path, FIG_W_PAIR, FIG_H_PAIR_MAX)
            fitted.append((path, w_mm, h_mm))
        cap_h = 14
        tallest = max(h for _, _, h in fitted)
        if self.get_y() + tallest + cap_h > self.page_break_trigger:
            self.add_page()
        top = self.get_y()
        col_w = (CONTENT_W - 6) / 2
        for i, (path, w_mm, h_mm) in enumerate(fitted):
            x = MARGIN + i * (col_w + 6) + (col_w - w_mm) / 2
            self.image(str(path), x=x, y=top, w=w_mm)
            self.set_xy(MARGIN + i * (col_w + 6), top + h_mm + 1.5)
            self.set_font("Helvetica", "I", 8.0)
            self.set_text_color(*GRAY)
            self.multi_cell(col_w, 3.9, sanitize(items[i][1]), align="C")
        self.set_y(min(top + tallest + cap_h, self.page_break_trigger - 8))
        self.ln(2.4)

    # ---------------------------------------------------------------- tables
    def add_table(self, headers: list[str], rows: list[list[str]],
                  col_widths: list[float], aligns: list[str] | None = None) -> None:
        aligns = aligns or ["LEFT"] + ["CENTER"] * (len(headers) - 1)
        head_style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)
        if self.get_y() + 18 + 6 * len(rows) > self.page_break_trigger:
            self.add_page()
        with self.table(col_widths=col_widths, text_align=aligns, line_height=4.6,
                        headings_style=head_style, borders_layout="ALL",
                        cell_fill_color=LIGHT, cell_fill_mode="ROWS") as tbl:
            hr = tbl.row()
            for htext in headers:
                hr.cell(htext)
            for row in rows:
                r = tbl.row()
                for cell in row:
                    r.cell(cell)
        self.ln(3)


def build_table(pdf: ReportPDF, key: str) -> None:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    if key == "dataset_summary":
        meta = json.loads(DATASET_META_PATH.read_text(encoding="utf-8"))
        headers, rows = dataset_rows(metrics, meta)
        pdf.add_table(headers, rows, [72, CONTENT_W - 72], ["LEFT", "LEFT"])
    elif key == "scenario_metrics":
        headers, rows = scenario_rows(metrics)
        widths = [40, 26, 18, 30, 22, 24, 22]
        scale = CONTENT_W / sum(widths)
        pdf.add_table(headers, rows, [w * scale for w in widths],
                      ["LEFT", "CENTER", "CENTER", "CENTER", "CENTER", "CENTER", "CENTER"])
    else:  # pragma: no cover - content-driven
        raise ValueError(f"Unknown table key: {key}")


def render() -> int:
    """Build the PDF; returns the final page count."""
    values = load_values()

    pdf = ReportPDF()
    pdf.title_page()

    for i, section in enumerate(rt.SECTIONS):
        if i == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.page_break_trigger - 42:
            # start a new page only when little space remains for the section head
            pdf.add_page()
        pdf.h1(section["heading"])
        for kind, payload in section["blocks"]:
            if kind == "p":
                pdf.para(payload.format(**values))
            elif kind == "bullets":
                pdf.bullets([item.format(**values) for item in payload])
            elif kind == "eq":
                pdf.equations(payload)
            elif kind == "refs":
                pdf.refs(payload)
            elif kind == "fig":
                name, caption = payload
                pdf.figure(name, caption.format(**values))
            elif kind == "figpair":
                pdf.figure_pair([(n, c.format(**values)) for n, c in payload])
            elif kind == "table":
                build_table(pdf, payload)
            else:  # pragma: no cover
                raise ValueError(f"Unknown block kind: {kind}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(REPORT_PATH)
    return pdf.page_no()


def scan_placeholders() -> list[str]:
    """Any unresolved {placeholder}-style tokens remaining in the PDF text."""
    reader = PdfReader(str(REPORT_PATH))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return sorted(set(re.findall(r"\{[a-z_][a-z0-9_]*\}", text)))


def main() -> None:
    pages = render()
    print(f"Report written to {REPORT_PATH} ({pages} pages)")
    problems = []
    if not 5 <= pages <= 8:
        problems.append(f"page count {pages} outside the required 5-8 range")
    leftovers = scan_placeholders()
    if leftovers:
        problems.append(f"unresolved placeholders in PDF text: {leftovers}")
    for problem in problems:
        print(f"ERROR: {problem}")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
