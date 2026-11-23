"""Seating problem modelled as a CSP.
Variables = students, Domains = available seats (row, col), 1-indexed.
HARD (CSP constraints): one seat per student (all-different), seat available,
   fixed seats, separated pairs not side-by-side.
SOFT (cost, lower is better): front-row preference for low CGPA, spread majors over rows,
   fewer moves compared to previous chart.
Search = backtracking + MRV + degree + forward checking (csp.py); soft costs guide VALUE ORDERING
(like LCV in AIMA); then hill-climbing local search (swaps) improves the soft cost."""
from csp import CSP, backtracking_search


class Config:
    def __init__(self, rows, cols, unavailable=(), separate=(), fixed=None,
                 front_rows=0, cgpa_threshold=0.0, spread_majors=True, prev=None,
                 w_front=3, w_major=1, w_move=2, hard_front=False):
        self.hard_front = hard_front              # True: front-row rule is HARD, not just a preference
        self.rows, self.cols = rows, cols
        self.unavailable = set(unavailable)
        self.separate = [tuple(p) for p in separate]
        self.fixed = dict(fixed or {})             # {student_id: (row, col)}
        self.front_rows, self.cgpa_threshold = front_rows, cgpa_threshold
        self.spread_majors = spread_majors
        self.prev = dict(prev) if prev else None   # previous chart {student_id: seat}
        self.w_front, self.w_major, self.w_move = w_front, w_major, w_move


class Result:
    def __init__(self, assignment, stats, message=""):
        self.assignment, self.stats, self.message = assignment, stats, message


class SeatingProblem:
    def __init__(self, students, cfg):
        self.students = {s.id: s for s in students}
        self.cfg = cfg
        self.seats = [(r, c) for r in range(1, cfg.rows + 1) for c in range(1, cfg.cols + 1)
                      if (r, c) not in cfg.unavailable]
        self.sep = {}
        for a, b in cfg.separate:
            self.sep.setdefault(a, set()).add(b)
            self.sep.setdefault(b, set()).add(a)

    # ---------- CSP construction ----------
    @staticmethod
    def adjacent(a, b):
        return a[0] == b[0] and abs(a[1] - b[1]) == 1

    def build_csp(self, smart_order=True):
        cfg = self.cfg
        # low CGPA first: breaks MRV ties so they get front seats first
        if cfg.cgpa_threshold and smart_order:
            variables = sorted(self.students, key=lambda s: (self.students[s].cgpa, s))
        else:
            variables = sorted(self.students)
        locked = set(cfg.fixed.values())
        domains = {}
        for s in variables:
            if s in cfg.fixed:
                domains[s] = [cfg.fixed[s]] if cfg.fixed[s] in self.seats else []
            else:
                domains[s] = [x for x in self.seats if x not in locked]
            if cfg.hard_front and cfg.cgpa_threshold and self.students[s].cgpa < cfg.cgpa_threshold:
                domains[s] = [x for x in domains[s] if x[0] <= cfg.front_rows]
        neighbors = {s: [o for o in variables if o != s] for s in variables}
        sep, adj = self.sep, self.adjacent

        def constraint(A, a, B, b):
            if a == b:                                   # all-different
                return False
            if B in sep.get(A, ()) and adj(a, b):        # separated pair
                return False
            return True
        return CSP(variables, domains, neighbors, constraint)

    # ---------- soft costs ----------
    def seat_cost(self, sid, seat, assign):
        """Cost of putting sid on seat given the other placements in assign."""
        cfg, s = self.cfg, self.students[sid]
        r, cost = seat[0], 0
        if cfg.cgpa_threshold and s.cgpa < cfg.cgpa_threshold and r > cfg.front_rows:
            cost += cfg.w_front * (r - cfg.front_rows)
        if cfg.spread_majors:
            cost += cfg.w_major * sum(1 for o, os in assign.items()
                                      if o != sid and os[0] == r and self.students[o].major == s.major)
        if cfg.prev and sid in cfg.prev and cfg.prev[sid] != seat:
            cost += cfg.w_move
        return cost

    def breakdown(self, assign):
        cfg = self.cfg
        low = [s for s in assign if cfg.cgpa_threshold and self.students[s].cgpa < cfg.cgpa_threshold]
        front_ok = sum(1 for s in low if assign[s][0] <= cfg.front_rows)
        front_pen = sum(cfg.w_front * max(0, assign[s][0] - cfg.front_rows) for s in low)
        counts = {}
        for s, (r, _) in assign.items():
            key = (self.students[s].major, r)
            counts[key] = counts.get(key, 0) + 1
        pairs = sum(k * (k - 1) // 2 for k in counts.values())
        ideal = 0                                         # minimum pairs if spread evenly
        for m in {k[0] for k in counts}:
            tot = sum(v for (mm, _), v in counts.items() if mm == m)
            q, rem = divmod(tot, cfg.rows)
            ideal += rem * ((q + 1) * q // 2) + (cfg.rows - rem) * (q * (q - 1) // 2)
        moved = sum(1 for s in assign if cfg.prev and s in cfg.prev and cfg.prev[s] != assign[s])
        return dict(low=len(low), front_ok=front_ok, front_pen=front_pen, pairs=pairs, ideal=ideal,
                    moved=moved, major_pen=cfg.w_major * pairs if cfg.spread_majors else 0,
                    move_pen=cfg.w_move * moved)

    def total_cost(self, assign):
        b = self.breakdown(assign)
        return b["front_pen"] + b["major_pen"] + b["move_pen"]

    def satisfaction(self, assign):
        """Soft-constraint satisfaction score 0-100 (mean of the active components)."""
        b, cfg, parts = self.breakdown(assign), self.cfg, []
        if cfg.cgpa_threshold and b["low"]:
            parts.append(b["front_ok"] / b["low"])
        if cfg.spread_majors:
            parts.append(1.0 if b["pairs"] == 0 else b["ideal"] / b["pairs"])
        if cfg.prev:
            parts.append(1 - b["moved"] / len(assign))
        return round(100 * sum(parts) / len(parts), 1) if parts else 100.0

    # ---------- validation ----------
    def hard_violations(self, assign):
        cfg, v = self.cfg, []
        for s in self.students:
            if s not in assign:
                v.append(f"{s} has no seat")
        if len(set(assign.values())) != len(assign):
            v.append("two students share a seat")
        for s, seat in assign.items():
            if seat not in self.seats:
                v.append(f"{s} is on unavailable/invalid seat {seat}")
            if s in cfg.fixed and cfg.fixed[s] != seat:
                v.append(f"{s} should be fixed at {cfg.fixed[s]}")
        for s, seat in assign.items():
            if s in self.students and not self._front_ok(s, seat):
                v.append(f"{s} (low CGPA) is not in the first {cfg.front_rows} rows")
        for a, b in cfg.separate:
            if a in assign and b in assign and self.adjacent(assign[a], assign[b]):
                v.append(f"{a} and {b} sit side by side")
        return v

    # ---------- local search (hill climbing, AIMA Ch.4) ----------
    def _front_ok(self, sid, seat):
        c = self.cfg
        return not (c.hard_front and c.cgpa_threshold and self.students[sid].cgpa < c.cgpa_threshold
                    and seat[0] > c.front_rows)

    def _ok_place(self, sid, assign):
        if not self._front_ok(sid, assign[sid]):
            return False
        return all(not self.adjacent(assign[sid], assign[p]) for p in self.sep.get(sid, ()) if p in assign)

    def improve(self, assign, max_sweeps=50):
        """First-improvement hill climbing: swap two students or move one to an empty seat.
        Only accepts moves that keep every hard constraint satisfied."""
        assign = dict(assign)
        movable = [s for s in assign if s not in self.cfg.fixed]
        best = self.total_cost(assign)
        for _ in range(max_sweeps):
            improved = False
            for i, a in enumerate(movable):
                used = set(assign.values())
                locked = set(self.cfg.fixed.values())
                for seat in [x for x in self.seats if x not in used and x not in locked]:
                    old = assign[a]
                    assign[a] = seat
                    c = self.total_cost(assign) if self._ok_place(a, assign) else None
                    if c is not None and c < best:
                        best, improved = c, True
                    else:
                        assign[a] = old
                for b in movable[i + 1:]:
                    assign[a], assign[b] = assign[b], assign[a]
                    c = self.total_cost(assign) if (self._ok_place(a, assign) and self._ok_place(b, assign)) else None
                    if c is not None and c < best:
                        best, improved = c, True
                    else:
                        assign[a], assign[b] = assign[b], assign[a]
            if not improved:
                break
        return assign

    # ---------- main entry ----------
    def solve(self, mrv=True, degree=True, fc=True, soft_order=True,
              node_limit=None, local_search=True, smart_order=True):
        if len(self.students) > len(self.seats):
            return Result(None, None, f"No feasible assignment: {len(self.students)} students but only {len(self.seats)} available seats.")
        cfg = self.cfg
        if cfg.hard_front and cfg.cgpa_threshold:       # quick counting (pigeonhole) check
            low = [s for s in self.students.values() if s.cgpa < cfg.cgpa_threshold]
            front = [x for x in self.seats if x[0] <= cfg.front_rows]
            if len(low) > len(front):
                return Result(None, None, f"No feasible assignment: {len(low)} students must sit in the first "
                              f"{cfg.front_rows} rows but only {len(front)} seats exist there.")
        csp = self.build_csp(smart_order)
        order = None
        if soft_order:
            order = lambda var, vals, assign: sorted(vals, key=lambda s: self.seat_cost(var, s, assign))
        sol, stats = backtracking_search(csp, mrv, degree, fc, order, node_limit)
        if sol is None:
            msg = "Search stopped (node limit reached)." if stats.cutoff else \
                  "No feasible assignment found: the hard constraints conflict."
            return Result(None, stats, msg)
        if local_search:
            sol = self.improve(sol)
        return Result(sol, stats, "Solved")
