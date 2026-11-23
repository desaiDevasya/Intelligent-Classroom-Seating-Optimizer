"""Student data structures and deterministic demo-data helpers."""
import random, csv


class Student:
    """One student record consumed by the seating CSP."""
    def __init__(self, sid, name, major, cgpa, year=""):
        self.id, self.name, self.major, self.cgpa, self.year = sid, name, major, float(cgpa), year

    def __repr__(self):
        return f"{self.id} {self.name} {self.major} {self.cgpa}"


FIRST = ["Aarav", "Diya", "Rohan", "Isha", "Karan", "Meera", "Neel", "Priya", "Raj", "Sneha",
         "Tanvi", "Utkarsh", "Vivek", "Anaya", "Dev", "Hetal", "Jay", "Krisha", "Manav", "Nisha",
         "Om", "Pooja", "Smit", "Zara"]
LAST = ["Patel", "Shah", "Mehta", "Desai", "Joshi", "Trivedi", "Sharma", "Gupta", "Modi", "Parikh"]
MAJORS = ["CSE", "ECE", "MECH", "BBA"]


def generate_students(n=48, seed=1):
    """Generate repeatable sample data for the demo and benchmark."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        cgpa = min(10.0, max(5.0, round(rnd.gauss(7.6, 1.0), 2)))
        out.append(Student(f"AU{2320001 + i}", name, rnd.choice(MAJORS), cgpa))
    return out


def load_csv(path):
    """Load the legacy CSV shape: ``name,id,major,cgpa``."""
    with open(path, newline="") as f:
        return [Student(r["id"], r["name"], r["major"], r["cgpa"]) for r in csv.DictReader(f)]
