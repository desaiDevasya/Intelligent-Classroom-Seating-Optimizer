"""Run:  python main.py          -> professor-facing desktop UI
        python main.py --demo   -> command-line demo
        python main.py --bench  -> compare basic vs heuristic backtracking"""
import sys, random
from data import generate_students
from seating import Config, SeatingProblem
from report import text_grid, validation_summary, moves, explain_moves, write_html


def demo():
    students = generate_students(48, seed=1)
    ids = [s.id for s in students]
    rnd = random.Random(7)
    separate = [tuple(rnd.sample(ids, 2)) for _ in range(5)]
    fixed = {ids[10]: (3, 5)}                       # one student locked to a seat
    base = dict(rows=6, cols=9, unavailable=[(1, 9), (6, 1)], separate=separate, fixed=fixed)

    print("=== STEP 1: initial chart (hard constraints + major spread) ===")
    p1 = SeatingProblem(students, Config(**base))
    r1 = p1.solve()
    if r1.assignment is None:
        print(r1.message); return
    print(text_grid(p1, r1.assignment)); print(validation_summary(p1, r1.assignment))
    print(f"Search: nodes={r1.stats.nodes} backtracks={r1.stats.backtracks} time={r1.stats.time:.3f}s\n")

    print("=== STEP 2: faculty adds 'CGPA < 7.0 preferably in first 2 rows' ===")
    p2 = SeatingProblem(students, Config(**base, front_rows=2, cgpa_threshold=7.0, prev=r1.assignment))
    r2 = p2.solve()
    if r2.assignment is None:
        print(r2.message); return
    print(text_grid(p2, r2.assignment)); print(validation_summary(p2, r2.assignment))
    notes = explain_moves(p2, r1.assignment, r2.assignment)
    print(f"\nMoved {len(moves(r1.assignment, r2.assignment))} students:")
    print("\n".join("  - " + n for n in notes))
    write_html("seating_report.html", p2, r1.assignment, r2.assignment, notes)
    print("\nSaved seating_report.html (open in browser)")


def bench():
    """Tight instance: 14 low-CGPA students must ALL sit in the first 2 rows (hard rule),
    and some of them must not sit side by side. Basic search fills the front with others first."""
    students = generate_students(48, seed=3)
    cg = sorted(s.cgpa for s in students)
    thr = cg[14]                                    # exactly 14 students below this
    low = [s.id for s in students if s.cgpa < thr]
    rnd = random.Random(5)
    seps = [tuple(rnd.sample(low, 2)) for _ in range(10)]
    cfg = Config(rows=6, cols=8, separate=seps, front_rows=2, cgpa_threshold=thr,
                 hard_front=True, spread_majors=False)
    p = SeatingProblem(students, cfg)
    print(f"{len(low)} low-CGPA students, 16 front seats, {len(seps)} separation pairs, node limit 200000")
    print(f"{'Method':<34}{'Solved':<9}{'Nodes':>9}{'Backtracks':>12}{'Time(s)':>9}")
    for name, kw in [("Basic backtracking", dict(mrv=False, fc=False)),
                     ("MRV only", dict(mrv=True, degree=False, fc=False)),
                     ("MRV + degree", dict(mrv=True, degree=True, fc=False)),
                     ("MRV + degree + forward checking", dict(mrv=True, degree=True, fc=True))]:
        r = p.solve(soft_order=False, local_search=False, node_limit=200000, smart_order=False, **kw)
        st = r.stats
        solved = "yes" if r.assignment else ("cutoff" if st.cutoff else "no")
        print(f"{name:<34}{solved:<9}{st.nodes:>9}{st.backtracks:>12}{st.time:>9.3f}")
    # infeasible case: 15th low student cannot fit if we only keep 1 front row of 8 seats
    p2 = SeatingProblem(students, Config(rows=6, cols=8, front_rows=1, cgpa_threshold=thr, hard_front=True))
    r = p2.solve(node_limit=20000)
    print("\nConflicting constraints example (14 low-CGPA students, 8 front seats, hard rule):")
    print("  ->", r.message)


if __name__ == "__main__":
    if "--bench" in sys.argv:
        bench()
    elif "--demo" in sys.argv:
        demo()
    else:
        from gui import SeatingApp
        SeatingApp().mainloop()
