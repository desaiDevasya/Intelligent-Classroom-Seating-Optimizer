"""Report rendering for terminal output and the optional HTML artifact.

The report deliberately connects the result to course theory so a submission
can explain not only *where* students were placed, but also *why* the engine
used its search strategy.
"""
import html

MAJOR_COLORS = {"CSE": "#cfe8ff", "ECE": "#d9f2d0", "MECH": "#ffe6c2", "BBA": "#f5d0f0"}

THEORY_EXPLANATION = (
    "CSP: students are variables and classroom seats are domains. "
    "Backtracking searches for a consistent assignment. MRV (Minimum Remaining "
    "Values) applies the fail-first principle, while the degree heuristic breaks "
    "ties using the most-constrained student. Forward checking removes values "
    "that became impossible after each assignment. Soft preferences guide value "
    "ordering, and hill climbing improves a feasible chart locally without "
    "breaking hard constraints."
)


def text_grid(p, assign):
    inv = {seat: sid for sid, seat in assign.items()}
    thr = p.cfg.cgpa_threshold
    lines = ["            " + "".join(f"Seat{c:<3}" for c in range(1, p.cfg.cols + 1)),
             "  [FRONT / BOARD]"]
    for r in range(1, p.cfg.rows + 1):
        row = f"Row {r}   "
        for c in range(1, p.cfg.cols + 1):
            if (r, c) in p.cfg.unavailable:
                cell = "XXX"
            elif (r, c) in inv:
                s = p.students[inv[(r, c)]]
                cell = inv[(r, c)][-3:] + ("*" if thr and s.cgpa < thr else " ")
            else:
                cell = "..."
            row += f"{cell:<7}"
        lines.append(row)
    lines.append("(cell = last 3 digits of enrollment ID; * = CGPA below threshold; XXX = unavailable; ... = empty)")
    return "\n".join(lines)


def validation_summary(p, assign):
    v = p.hard_violations(assign)
    b = p.breakdown(assign)
    out = ["Hard constraints: " + ("ALL SATISFIED" if not v else f"{len(v)} VIOLATION(S)")]
    out += ["   - " + x for x in v]
    if p.cfg.cgpa_threshold:
        out.append(f"Front-row preference: {b['front_ok']}/{b['low']} low-CGPA students in first {p.cfg.front_rows} rows")
    if p.cfg.spread_majors:
        out.append(f"Major spread: {b['pairs']} same-major pairs in a row (best possible about {b['ideal']})")
    if p.cfg.prev:
        out.append(f"Students moved from previous chart: {b['moved']}")
    out.append(f"Weighted soft cost: {p.total_cost(assign)}  |  Soft satisfaction score: {p.satisfaction(assign)}/100")
    out.append("Course theory: " + THEORY_EXPLANATION)
    return "\n".join(out)


def moves(old, new):
    return {s: (old[s], new[s]) for s in new if s in old and old[s] != new[s]}


def alphabetical_assignment(p):
    """Build a transparent alphabetical baseline for the same classroom.

    Fixed seats are respected so the comparison changes only the placement
    strategy. The baseline is intentionally not repaired for other rules;
    violations are evidence used in the comparison report.
    """
    assignment = {sid: seat for sid, seat in p.cfg.fixed.items() if seat in p.seats}
    used = set(assignment.values())
    free_seats = [seat for seat in p.seats if seat not in used]
    remaining = sorted((student for sid, student in p.students.items() if sid not in assignment),
                       key=lambda student: (student.name.casefold(), student.id))
    return {**assignment, **{student.id: seat for student, seat in zip(remaining, free_seats)}}


def comparison_summary(p, optimized, baseline):
    """Explain the optimized-vs-alphabetical result using recorded metrics."""
    opt, alpha = p.breakdown(optimized), p.breakdown(baseline)
    opt_v, alpha_v = p.hard_violations(optimized), p.hard_violations(baseline)
    lines = ["Alphabetical baseline comparison (same students and classroom):"]
    lines.append(f"- Hard violations: optimized {len(opt_v)} vs alphabetical {len(alpha_v)}")
    if p.cfg.cgpa_threshold:
        lines.append(f"- Low-GPA students in front rows: optimized {opt['front_ok']}/{opt['low']} vs alphabetical {alpha['front_ok']}/{alpha['low']}")
    if p.cfg.spread_majors:
        lines.append(f"- Same-major pairs in a row: optimized {opt['pairs']} vs alphabetical {alpha['pairs']} (lower is better)")
    lines.append(f"- Weighted soft cost: optimized {p.total_cost(optimized)} vs alphabetical {p.total_cost(baseline)} (lower is better)")
    if p.total_cost(optimized) < p.total_cost(baseline):
        lines.append("Conclusion: the generated arrangement is better for the selected soft preferences because its measured weighted cost is lower.")
    elif p.total_cost(optimized) > p.total_cost(baseline):
        lines.append("Conclusion: alphabetical ordering has the lower measured weighted cost for these settings; the optimizer did not improve this instance.")
    else:
        lines.append("Conclusion: both arrangements have the same measured weighted cost for these settings.")
    return "\n".join(lines)


def explain_moves(p, old, new):
    cfg, out = p.cfg, []
    for s, (a, b) in sorted(moves(old, new).items(), key=lambda x: x[1][1]):
        st = p.students[s]
        if cfg.cgpa_threshold and st.cgpa < cfg.cgpa_threshold and b[0] <= cfg.front_rows < a[0]:
            why = f"front-row preference (CGPA {st.cgpa} < {cfg.cgpa_threshold})"
        elif cfg.cgpa_threshold and st.cgpa >= cfg.cgpa_threshold and a[0] <= cfg.front_rows < b[0]:
            why = "gave up a front seat to a student with lower CGPA"
        else:
            why = "swapped to make room for another move / spread the major across rows"
        out.append(f"{st.name} ({s}) moved Row {a[0]} Seat {a[1]} -> Row {b[0]} Seat {b[1]}: {why}")
    return out


def _html_grid(p, assign, old=None):
    inv = {seat: sid for sid, seat in assign.items()}
    thr, rows = p.cfg.cgpa_threshold, ["<table>"]
    for r in range(1, p.cfg.rows + 1):
        rows.append(f"<tr><th>Row {r}</th>")
        for c in range(1, p.cfg.cols + 1):
            if (r, c) in p.cfg.unavailable:
                rows.append("<td class='x'>unavailable</td>")
            elif (r, c) in inv:
                s = p.students[inv[(r, c)]]
                mv = " moved" if old and old.get(s.id) != (r, c) else ""
                low = " low" if thr and s.cgpa < thr else ""
                rows.append(f"<td class='{mv}{low}' style='background:{MAJOR_COLORS.get(s.major,'#eee')}'>"
                            f"{html.escape(s.name)}<br><small>{s.id[-3:]} | {s.major} | {s.cgpa}</small></td>")
            else:
                rows.append("<td class='x'>empty</td>")
        rows.append("</tr>")
    rows.append("</table>")
    return "".join(rows)


def write_html(path, p, old, new, notes, baseline=None):
    css = ("body{font-family:Arial;margin:20px}table{border-collapse:collapse;margin:10px 0}"
           "td,th{border:1px solid #999;padding:4px 6px;font-size:12px;text-align:center;min-width:80px}"
           "td.x{background:#ddd;color:#777}td.low{border:2px solid #c00}td.moved{outline:3px solid #f90}"
           "pre{background:#f4f4f4;padding:8px}")
    comparison = ""
    if baseline is not None:
        comparison = f"<h3>Alphabetical comparison</h3><pre>{html.escape(comparison_summary(p, new, baseline))}</pre>"
    body = (f"<h2>Original chart</h2>{_html_grid(p, old)}<h2>Revised chart</h2>{_html_grid(p, new, old)}"
            f"<p>Red border = CGPA below {p.cfg.cgpa_threshold}; orange outline = moved student; "
            f"colour = major. Board/front is at Row 1.</p><h3>Validation</h3><pre>{html.escape(validation_summary(p, new))}</pre>"
            f"<h3>Course theory</h3><p>{html.escape(THEORY_EXPLANATION)}</p>"
            f"{comparison}<h3>Explanations</h3><pre>{html.escape(chr(10).join(notes))}</pre>")
    with open(path, "w") as f:
        f.write(f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
