"""Generic CSP solver (AIMA Ch.6 style): backtracking + MRV + degree + forward checking.
Written from scratch, no libraries. Used by seating.py."""
import sys, time
sys.setrecursionlimit(10000)


class CSP:
    """A finite-domain CSP: variables, candidate values, neighbors, and a rule."""
    """variables: list; domains: {var: list of values}; neighbors: {var: list of vars};
    constraint(A, a, B, b) -> True if A=a and B=b are allowed together."""
    def __init__(self, variables, domains, neighbors, constraint):
        self.variables = variables
        self.domains = domains
        self.neighbors = neighbors
        self.constraint = constraint


class Stats:
    """Search instrumentation shown in the demo and generated reports."""
    def __init__(self):
        self.nodes = 0         # number of assignments tried
        self.backtracks = 0    # number of times we undid an assignment
        self.time = 0.0
        self.cutoff = False    # True if node_limit was hit


def backtracking_search(csp, mrv=True, degree=True, fc=True,
                        order_values=None, node_limit=None):
    """Returns (assignment or None, Stats).
    mrv: pick variable with fewest legal values (ties -> degree heuristic if degree=True)
    fc: forward checking (prune neighbours' domains after each assignment)
    order_values(var, values, assignment) -> list: value ordering (e.g. soft-constraint cost)."""
    stats = Stats()
    start = time.time()
    domains = {v: list(d) for v, d in csp.domains.items()}
    assignment = {}

    if any(len(d) == 0 for d in domains.values()):      # empty domain => impossible
        stats.time = time.time() - start
        return None, stats

    def select_var():
        unassigned = [v for v in csp.variables if v not in assignment]
        if not mrv:
            return unassigned[0]                       # static order
        if degree:
            return min(unassigned, key=lambda v: (
                len(domains[v]),
                -sum(1 for n in csp.neighbors[v] if n not in assignment)))
        return min(unassigned, key=lambda v: len(domains[v]))

    def consistent(var, val):
        return all(csp.constraint(var, val, n, assignment[n])
                   for n in csp.neighbors[var] if n in assignment)

    def backtrack():
        if len(assignment) == len(csp.variables):
            return True
        if node_limit is not None and stats.nodes >= node_limit:
            stats.cutoff = True
            return False
        var = select_var()
        values = list(domains[var])
        if order_values:
            values = order_values(var, values, assignment)
        for val in values:
            if not consistent(var, val):
                continue
            stats.nodes += 1
            assignment[var] = val
            removed, ok = [], True
            if fc:                                      # forward checking
                for n in csp.neighbors[var]:
                    if n in assignment:
                        continue
                    for x in domains[n][:]:
                        if not csp.constraint(var, val, n, x):
                            domains[n].remove(x)
                            removed.append((n, x))
                    if not domains[n]:                  # domain wipe-out -> fail early
                        ok = False
                        break
            if ok and backtrack():
                return True
            for n, x in removed:                        # undo pruning
                domains[n].append(x)
            del assignment[var]
            stats.backtracks += 1
            if stats.cutoff:
                return False
        return False

    solved = backtrack()
    stats.time = time.time() - start
    return (dict(assignment) if solved else None), stats
