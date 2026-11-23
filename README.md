# Intelligent-Classroom-Seating-Optimizer
Seating is modeled as a finite-domain CSP: students are variables, (row, column) seats are domains, and rules are constraints. Backtracking finds feasibility using MRV, degree heuristics, forward checking, and low-cost value ordering. Hill climbing refines the result via valid swaps, though global optimality is not guaranteed.
