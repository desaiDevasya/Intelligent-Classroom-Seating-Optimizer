"""Desktop UI for the classroom seating optimizer.

Run with: python gui.py

The interface intentionally uses only Python's standard library.  XLSX files
are read directly from their XML package, so the professor's laptop does not
need pandas or openpyxl installed.
"""
import csv
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

from data import Student
from report import text_grid, validation_summary, write_html
from seating import Config, SeatingProblem


class ScrollableFrame(ttk.Frame):
    """A frame with a dependable vertical scrollbar for smaller laptop screens."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, event):
        if self.winfo_containing(event.x_root, event.y_root) is not None:
            self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")


def _clean_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _read_xlsx(path):
    """Read a simple first-sheet XLSX using the standard library."""
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with ZipFile(path) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall("a:si", ns)]
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ET.fromstring(book.read(sheet_name))
        rows = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            values = []
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "A1")
                match = re.match(r"([A-Z]+)", ref)
                col = 0
                for letter in match.group(1):
                    col = col * 26 + ord(letter) - 64
                while len(values) < col:
                    values.append("")
                value = cell.find("a:v", ns)
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values[col - 1] = text
            rows.append(values)
    if not rows:
        return []
    headers = [_clean_header(x) for x in rows[0]]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in rows[1:]]


def _read_student_file(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        rows = _read_xlsx(path)
    elif suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            rows = [{_clean_header(k): v for k, v in row.items()} for row in reader]
    else:
        raise ValueError("Choose an .xlsx or .csv file. Old .xls files should be saved as .xlsx first.")
    aliases = {
        "id": ("id", "studentid", "enrollmentid", "enrollmentnumber", "rollno", "rollnumber"),
        "first": ("firstname", "first", "givenname"),
        "last": ("lastname", "last", "surname", "familyname"),
        "major": ("major", "department", "branch"),
        "gpa": ("gpa", "cgpa", "gradepointaverage"),
        "year": ("year", "academicyear", "studyyear"),
    }
    def get(row, key):
        for name in aliases[key]:
            if name in row:
                return row[name]
        return ""
    students = []
    for number, row in enumerate(rows, 1):
        sid = str(get(row, "id")).strip() or f"AU{2320000 + number:07d}"
        first, last, major, gpa = get(row, "first"), get(row, "last"), get(row, "major"), get(row, "gpa")
        if not (str(first).strip() and str(last).strip() and str(major).strip() and str(gpa).strip()):
            continue
        students.append(Student(sid, f"{first} {last}", str(major).strip(), float(gpa), get(row, "year")))
    if not students:
        raise ValueError("No valid student rows found. Required columns: first name, last name, major, GPA.")
    if len({student.id for student in students}) != len(students):
        raise ValueError("The student file contains duplicate IDs. IDs must be unique.")
    return students


class SeatingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Intelligent Classroom Seating Optimizer")
        self.geometry("1280x820")
        self.minsize(1050, 700)
        self.students = []
        self.last_problem = None
        self.last_assignment = None
        self._build_style()
        self._build_ui()
        self._refresh_students()
        self._draw_preview()

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#153b5b")
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), foreground="#153b5b")
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))

    def _build_ui(self):
        header = ttk.Frame(self, padding=(20, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Classroom Seating Optimizer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Enter the class rules, preview the room, then generate a validated seating chart.").pack(anchor="w")

        self.status = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.status, foreground="#426b80").pack(anchor="e")
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        left_scroll = ScrollableFrame(body)
        right_scroll = ScrollableFrame(body)
        left, right = left_scroll.content, right_scroll.content
        left.configure(padding=10); right.configure(padding=10)
        body.add(left_scroll, weight=3); body.add(right_scroll, weight=2)
        self._build_students(left)
        self._build_rules(left)
        self._build_preview(right)

    def _build_students(self, parent):
        box = ttk.LabelFrame(parent, text="1. Students", padding=10)
        box.pack(fill="both", expand=True)
        actions = ttk.Frame(box); actions.pack(fill="x")
        ttk.Button(actions, text="Load Excel / CSV", command=self._load_students).pack(side="left")
        ttk.Button(actions, text="Add student", command=self._new_student_form).pack(side="left", padx=8)
        ttk.Button(actions, text="Remove selected", command=self._remove_student).pack(side="left")
        ttk.Label(actions, text="  Excel columns: ID, first name, last name, major, GPA, year").pack(side="left")
        columns = ("id", "first", "last", "major", "gpa", "year")
        self.student_tree = ttk.Treeview(box, columns=columns, show="headings", height=12)
        labels = {"id": "ID", "first": "First name", "last": "Last name", "major": "Major", "gpa": "GPA", "year": "Year"}
        widths = {"id": 75, "first": 120, "last": 120, "major": 90, "gpa": 60, "year": 60}
        for col in columns:
            self.student_tree.heading(col, text=labels[col])
            self.student_tree.column(col, width=widths[col], anchor="center")
        self.student_tree.pack(fill="both", expand=True, pady=(10, 0))
        self.student_tree.bind("<<TreeviewSelect>>", self._select_student)
        ttk.Label(box, text="Select a row below to edit it, or choose Add student.", foreground="#666").pack(anchor="w", pady=(5, 0))

        form = ttk.LabelFrame(box, text="Student details", padding=7)
        form.pack(fill="x", pady=(8, 0))
        self.form_vars = {key: tk.StringVar() for key in ("id", "first", "last", "major", "gpa", "year")}
        fields = (("id", "Student ID"), ("first", "First name"), ("last", "Last name"), ("major", "Major"), ("gpa", "GPA"), ("year", "Year"))
        for index, (key, label) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=0, column=index, sticky="w", padx=3)
            entry = ttk.Entry(form, textvariable=self.form_vars[key], width=15 if key not in ("gpa", "year") else 8)
            entry.grid(row=1, column=index, sticky="ew", padx=3)
            if key == "id":
                self.id_entry = entry
                entry.bind("<FocusIn>", self._clear_id_placeholder)
                entry.bind("<FocusOut>", self._restore_id_placeholder)
        self.editing_id = None
        self._set_id_placeholder()
        form_buttons = ttk.Frame(form); form_buttons.grid(row=2, column=0, columnspan=6, sticky="w", pady=(7, 0))
        ttk.Button(form_buttons, text="Save student", command=self._save_student_form).pack(side="left")
        ttk.Button(form_buttons, text="Clear form", command=self._new_student_form).pack(side="left", padx=7)

    def _build_rules(self, parent):
        box = ttk.LabelFrame(parent, text="2. Classroom and constraints", padding=10)
        box.pack(fill="x", pady=(12, 0))
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Label(top, text="Rows").pack(side="left"); self.rows_var = tk.IntVar(value=6); ttk.Spinbox(top, from_=1, to=30, textvariable=self.rows_var, width=5, command=self._draw_preview).pack(side="left", padx=(4, 15))
        ttk.Label(top, text="Columns").pack(side="left"); self.cols_var = tk.IntVar(value=9); ttk.Spinbox(top, from_=1, to=30, textvariable=self.cols_var, width=5, command=self._draw_preview).pack(side="left", padx=(4, 15))
        ttk.Label(top, text="Unavailable seats (e.g. 1,3; 4,6)").pack(side="left"); self.unavailable_var = tk.StringVar(); ttk.Entry(top, textvariable=self.unavailable_var, width=25).pack(side="left", padx=5)
        self.unavailable_var.trace_add("write", lambda *_: self._draw_preview())

        hard = ttk.LabelFrame(box, text="Hard restrictions", padding=7); hard.pack(fill="x", pady=(10, 5))
        ttk.Label(hard, text="Separated student IDs (e.g. STU001,STU002; STU003,STU004)").pack(anchor="w")
        self.separate_var = tk.StringVar(); ttk.Entry(hard, textvariable=self.separate_var).pack(fill="x", pady=(2, 5))
        ttk.Label(hard, text="Fixed seats (e.g. STU001=2,3; STU004=1,1)").pack(anchor="w")
        self.fixed_var = tk.StringVar(); ttk.Entry(hard, textvariable=self.fixed_var).pack(fill="x", pady=(2, 5))
        row = ttk.Frame(hard); row.pack(fill="x")
        self.hard_front_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Low-GPA students must be in front rows", variable=self.hard_front_var).pack(side="left")
        ttk.Label(row, text="Front rows").pack(side="left", padx=(20, 4)); self.front_rows_var = tk.IntVar(value=2); ttk.Spinbox(row, from_=1, to=30, textvariable=self.front_rows_var, width=5).pack(side="left")
        ttk.Label(row, text="GPA below").pack(side="left", padx=(15, 4)); self.threshold_var = tk.DoubleVar(value=7.0); ttk.Spinbox(row, from_=0, to=10, increment=.1, textvariable=self.threshold_var, width=5).pack(side="left")

        soft = ttk.LabelFrame(box, text="Soft preferences", padding=7); soft.pack(fill="x", pady=(5, 0))
        self.spread_var = tk.BooleanVar(value=True); ttk.Checkbutton(soft, text="Spread students from the same major across rows", variable=self.spread_var).pack(anchor="w")
        self.front_soft_var = tk.BooleanVar(value=True); ttk.Checkbutton(soft, text="Prefer low-GPA students in front rows", variable=self.front_soft_var).pack(anchor="w")
        weights = ttk.Frame(soft); weights.pack(fill="x", pady=(4, 0))
        ttk.Label(weights, text="Front preference weight").pack(side="left"); self.front_weight_var = tk.IntVar(value=3); ttk.Spinbox(weights, from_=0, to=20, textvariable=self.front_weight_var, width=4).pack(side="left", padx=5)
        ttk.Label(weights, text="Major spread weight").pack(side="left", padx=(18, 0)); self.major_weight_var = tk.IntVar(value=1); ttk.Spinbox(weights, from_=0, to=20, textvariable=self.major_weight_var, width=4).pack(side="left", padx=5)
        ttk.Button(box, text="Generate seating chart", style="Primary.TButton", command=self._generate).pack(fill="x", pady=(12, 0))

    def _build_preview(self, parent):
        box = ttk.LabelFrame(parent, text="Live classroom preview", padding=10); box.pack(fill="both", expand=True)
        ttk.Label(box, text="Row 1 is the front / board. Red cells are unavailable.", foreground="#666").pack(anchor="w")
        self.canvas = tk.Canvas(box, background="white", highlightthickness=1, highlightbackground="#cbd8df")
        self.canvas.pack(fill="both", expand=True, pady=8)
        self.result = tk.Text(box, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        self.result.pack(fill="x")
        buttons = ttk.Frame(box); buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Save HTML report", command=self._save_report).pack(side="right")

    def _build_preview_grid(self, rows, cols, unavailable):
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 400); height = max(self.canvas.winfo_height(), 250)
        cell_w = min(115, max(35, (width - 50) / max(cols, 1))); cell_h = min(48, max(28, (height - 45) / max(rows, 1)))
        x0, y0 = 35, 35
        self.canvas.create_text(width / 2, 13, text="FRONT / BOARD", fill="#153b5b", font=("Segoe UI", 10, "bold"))
        for r in range(1, rows + 1):
            self.canvas.create_text(16, y0 + (r - .5) * cell_h, text=str(r), fill="#444")
            for c in range(1, cols + 1):
                x1, y1 = x0 + (c - 1) * cell_w, y0 + (r - 1) * cell_h
                unavailable_cell = (r, c) in unavailable
                self.canvas.create_rectangle(x1, y1, x1 + cell_w - 3, y1 + cell_h - 3, fill="#f3b3b3" if unavailable_cell else "#edf5f8", outline="#78909c")
                self.canvas.create_text(x1 + cell_w / 2, y1 + cell_h / 2, text="X" if unavailable_cell else f"{r},{c}", fill="#8b1e1e" if unavailable_cell else "#527080")

    def _draw_preview(self):
        try:
            rows, cols = max(1, int(self.rows_var.get())), max(1, int(self.cols_var.get()))
        except (ValueError, tk.TclError):
            return
        self._build_preview_grid(rows, cols, self._parse_seats(self.unavailable_var.get()))

    def _parse_seats(self, value):
        seats = set()
        for piece in re.split(r"[;\n]+", value):
            match = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", piece)
            if match: seats.add((int(match.group(1)), int(match.group(2))))
        return seats

    def _refresh_students(self):
        for item in self.student_tree.get_children(): self.student_tree.delete(item)
        for s in self.students: self.student_tree.insert("", "end", values=(s.id, *s.name.split(" ", 1), s.major, s.cgpa, getattr(s, "year", "")))
        self.status.set(f"{len(self.students)} student(s) loaded")

    def _new_student_form(self):
        self.editing_id = None
        for variable in self.form_vars.values(): variable.set("")
        self._set_id_placeholder()
        self.status.set("Enter a new student, then press Save student")

    def _set_id_placeholder(self):
        self.form_vars["id"].set("AUXXXXXXX")
        self.id_entry.configure(foreground="#777")

    def _clear_id_placeholder(self, _event=None):
        if self.form_vars["id"].get() == "AUXXXXXXX":
            self.form_vars["id"].set("")
            self.id_entry.configure(foreground="#111")

    def _restore_id_placeholder(self, _event=None):
        if not self.form_vars["id"].get().strip():
            self._set_id_placeholder()

    def _select_student(self, _event=None):
        selected = self.student_tree.selection()
        if not selected: return
        values = self.student_tree.item(selected[0], "values")
        self.editing_id = values[0]
        for key, value in zip(("id", "first", "last", "major", "gpa", "year"), values): self.form_vars[key].set(value)
        self.id_entry.configure(foreground="#111")
        self.status.set(f"Editing {self.editing_id}; update the fields and press Save student")

    def _save_student_form(self):
        values = {key: variable.get().strip() for key, variable in self.form_vars.items()}
        if values["id"] == "AUXXXXXXX" or not all(values[key] for key in ("id", "first", "last", "major", "gpa")):
            messagebox.showerror("Incomplete student", "Student ID, first name, last name, major, and GPA are required.")
            return
        if any(s.id == values["id"] and s.id != self.editing_id for s in self.students):
            messagebox.showerror("Duplicate student ID", "Every student must have a unique ID.")
            return
        try:
            gpa = float(values["gpa"])
        except ValueError:
            messagebox.showerror("Invalid GPA", "GPA must be a number.")
            return
        if not 0 <= gpa <= 10:
            messagebox.showerror("Invalid GPA", "GPA must be between 0 and 10.")
            return
        if self.editing_id:
            self.students = [Student(values["id"], f"{values['first']} {values['last']}", values["major"], gpa, values["year"]) if s.id == self.editing_id else s for s in self.students]
        else:
            self.students.append(Student(values["id"], f"{values['first']} {values['last']}", values["major"], gpa, values["year"]))
        self._refresh_students()
        self._new_student_form()

    def _remove_student(self):
        selected = self.student_tree.selection()
        ids = {self.student_tree.item(x, "values")[0] for x in selected}
        self.students = [s for s in self.students if s.id not in ids]
        self._refresh_students()

    def _load_students(self):
        path = filedialog.askopenfilename(filetypes=[("Excel workbook", "*.xlsx"), ("CSV file", "*.csv")])
        if not path: return
        try:
            self.students = _read_student_file(path); self._refresh_students(); self.status.set(f"Loaded {len(self.students)} students from {Path(path).name}")
        except (ValueError, OSError, BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
            messagebox.showerror("Could not load students", str(exc))

    def _parse_pairs(self, value):
        pairs = []
        for part in re.split(r"[;\n]+", value):
            ids = [x.strip() for x in part.split(",") if x.strip()]
            if len(ids) == 2: pairs.append(tuple(ids))
        return pairs

    def _parse_fixed(self, value):
        fixed = {}
        for part in re.split(r"[;\n]+", value):
            if not part.strip():
                continue
            match = re.fullmatch(r"\s*([^=]+?)\s*=\s*(\d+)\s*,\s*(\d+)\s*", part)
            if not match:
                raise ValueError("Fixed seats must use the format STUDENT_ID=row,column.")
            fixed[match.group(1).strip()] = (int(match.group(2)), int(match.group(3)))
        return fixed

    def _generate(self):
        try:
            if not self.students: raise ValueError("Load or add at least one student first.")
            rows, cols = int(self.rows_var.get()), int(self.cols_var.get())
            unavailable = self._parse_seats(self.unavailable_var.get())
            if any(r < 1 or r > rows or c < 1 or c > cols for r, c in unavailable): raise ValueError("Unavailable seats must be inside the classroom layout.")
            fixed = self._parse_fixed(self.fixed_var.get())
            known_ids = {s.id for s in self.students}
            unknown_fixed = sorted(set(fixed) - known_ids)
            if unknown_fixed:
                raise ValueError("Fixed-seat IDs not found in the student list: " + ", ".join(unknown_fixed))
            cfg = Config(rows, cols, unavailable=unavailable, separate=self._parse_pairs(self.separate_var.get()), fixed=fixed, front_rows=int(self.front_rows_var.get()), cgpa_threshold=float(self.threshold_var.get()), spread_majors=self.spread_var.get(), w_front=int(self.front_weight_var.get()), w_major=int(self.major_weight_var.get()), hard_front=self.hard_front_var.get())
            problem = SeatingProblem(self.students, cfg); result = problem.solve()
            if result.assignment is None:
                self._show_result(result.message); self.status.set("No feasible chart")
                return
            self.last_problem, self.last_assignment = problem, result.assignment
            self._show_result(text_grid(problem, result.assignment) + "\n\n" + validation_summary(problem, result.assignment) + f"\n\nSearch nodes: {result.stats.nodes} | Backtracks: {result.stats.backtracks}")
            self._draw_assignment(problem, result.assignment); self.status.set("Chart generated and validated")
        except (ValueError, tk.TclError) as exc: messagebox.showerror("Check your inputs", str(exc))

    def _draw_assignment(self, problem, assignment):
        self._build_preview_grid(problem.cfg.rows, problem.cfg.cols, problem.cfg.unavailable)
        by_seat = {seat: sid for sid, seat in assignment.items()}
        for seat, sid in by_seat.items():
            r, c = seat; width = max(self.canvas.winfo_width(), 400); height = max(self.canvas.winfo_height(), 250)
            cell_w = min(115, max(35, (width - 50) / problem.cfg.cols)); cell_h = min(48, max(28, (height - 45) / problem.cfg.rows)); x = 35 + (c - 1) * cell_w; y = 35 + (r - 1) * cell_h
            self.canvas.create_rectangle(x, y, x + cell_w - 3, y + cell_h - 3, fill="#cfe8ff", outline="#3575a8", width=2)
            self.canvas.create_text(x + cell_w / 2, y + cell_h / 2, text=sid[-5:], fill="#153b5b")

    def _show_result(self, text):
        self.result.configure(state="normal"); self.result.delete("1.0", "end"); self.result.insert("1.0", text); self.result.configure(state="disabled")

    def _save_report(self):
        if not self.last_problem: messagebox.showinfo("Nothing to save", "Generate a seating chart first."); return
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML report", "*.html")], initialfile="seating_report.html")
        if path:
            write_html(path, self.last_problem, {}, self.last_assignment, [])
            messagebox.showinfo("Report saved", f"Saved report to:\n{path}")


if __name__ == "__main__":
    SeatingApp().mainloop()
