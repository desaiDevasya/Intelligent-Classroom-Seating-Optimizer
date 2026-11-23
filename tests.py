"""Regression tests for the hard constraints and basic solver behavior."""

import unittest
from data import Student, generate_students
from seating import Config, SeatingProblem


def S(i, major="CSE", cgpa=8.0):
    return Student(f"S{i}", f"N{i}", major, cgpa)


class T(unittest.TestCase):
    def test_too_many_students(self):
        r = SeatingProblem([S(1), S(2), S(3)], Config(1, 2)).solve()
        self.assertIsNone(r.assignment); self.assertIn("No feasible", r.message)

    def test_separation_conflict(self):
        r = SeatingProblem([S(1), S(2)], Config(1, 2, separate=[("S1", "S2")])).solve()
        self.assertIsNone(r.assignment)

    def test_fixed_and_unavailable(self):
        cfg = Config(2, 3, unavailable=[(1, 1)], fixed={"S1": (2, 2)})
        r = SeatingProblem([S(1), S(2), S(3)], cfg).solve()
        p = SeatingProblem([S(1), S(2), S(3)], cfg)
        self.assertEqual(r.assignment["S1"], (2, 2)); self.assertEqual(p.hard_violations(r.assignment), [])

    def test_front_preference(self):
        studs = [S(i, cgpa=6.0 if i < 4 else 9.0) for i in range(12)]
        p = SeatingProblem(studs, Config(4, 3, front_rows=1, cgpa_threshold=7.0))
        r = p.solve()
        self.assertEqual(sum(1 for s in ("S0", "S1", "S2") if r.assignment[s][0] == 1), 3)

    def test_demo_size(self):
        p = SeatingProblem(generate_students(48), Config(6, 9))
        r = p.solve(); self.assertEqual(p.hard_violations(r.assignment), [])


if __name__ == "__main__":
    unittest.main()
