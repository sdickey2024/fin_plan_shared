#!/usr/bin/env python3
"""
json_form_editor.py
A reusable, schema-driven Tkinter editor for your JSON files (user/scenario).

Key ideas:
- Pass in a Python dict 'data' and an optional 'schema' describing structure.
- The editor builds form widgets (string/number/bool/date, dicts, lists).
- For free-form dicts (like 'expenses' or 'changes'), it shows a key/value table.
- get_value() returns the edited JSON object.

Schema (light JSON-Schema-ish):
{
  "type": "object",
  "title": "User",
  "properties": {
      "person": { "type": "object", "properties": { "name": {"type":"string"}, "age":{"type":"integer"} } },
      "expenses": { "type":"object", "title":"Expenses", "additionalProperties": {"type":"number"} },
      "life_events": { "type":"array", "items": { "type":"object", ... } }
  }
}

Supported keys:
- type: "object" | "array" | "string" | "integer" | "number" | "boolean"
- title: Optional label
- enum: for strings/numbers to show a dropdown
- format: "date" (yyyy-mm-dd, light validation)
- properties: (object) dict of name -> subschema
- additionalProperties: (object) for key/value dicts (values follow subschema)
- items: (array) subschema for list items
- default: default value if missing
"""

import tkinter as tk
from tkinter import ttk, messagebox
import re
import copy

# --------- Minimal helper casting ---------
def _to_number(s):
    try:
        if s.strip() == "":
            return None
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)
    except Exception:
        return None

def _to_bool(s):
    s2 = str(s).strip().lower()
    if s2 in ("true", "1", "yes", "y", "on"):
        return True
    if s2 in ("false", "0", "no", "n", "off"):
        return False
    return None

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# --------- Field editors ---------
class _Labeled(tk.Frame):
    def __init__(self, master, label=None):
        super().__init__(master)
        self.columnconfigure(1, weight=1)
        if label:
            ttk.Label(self, text=label).grid(row=0, column=0, padx=(0,8), sticky="w")

class StringEditor(_Labeled):
    def __init__(self, master, label=None, value=""):
        super().__init__(master, label)
        self.var = tk.StringVar(value="" if value is None else str(value))
        self.entry = ttk.Entry(self, textvariable=self.var)
        self.entry.grid(row=0, column=1, sticky="ew")

    def get(self):
        return self.var.get()

class EnumEditor(_Labeled):
    def __init__(self, master, label=None, value=None, choices=()):
        super().__init__(master, label)
        if value not in choices and choices:
            value = choices[0]
        self.var = tk.StringVar(value=value)
        self.opt = ttk.OptionMenu(self, self.var, self.var.get(), *choices)
        self.opt.grid(row=0, column=1, sticky="w")

    def get(self):
        return self.var.get()

class NumberEditor(_Labeled):
    def __init__(self, master, label=None, value=None):
        super().__init__(master, label)
        self.var = tk.StringVar(value="" if value is None else str(value))
        vcmd = (self.register(self._validate), "%P")
        self.entry = ttk.Entry(self, textvariable=self.var, validate="key", validatecommand=vcmd)
        self.entry.grid(row=0, column=1, sticky="ew")

    def _validate(self, s):
        if s.strip() == "":
            return True
        try:
            float(s)
            return True
        except Exception:
            return False

    def get(self):
        s = self.var.get()
        n = _to_number(s)
        return n if n is not None else s  # if user typed non-numeric, return raw

class IntegerEditor(NumberEditor):
    def get(self):
        s = self.var.get()
        n = _to_number(s)
        if isinstance(n, float):
            try:
                return int(n)
            except Exception:
                return s
        return n if n is not None else s

class BoolEditor(_Labeled):
    def __init__(self, master, label=None, value=False):
        super().__init__(master, label)
        self.var = tk.BooleanVar(value=bool(value))
        self.cb = ttk.Checkbutton(self, variable=self.var)
        self.cb.grid(row=0, column=1, sticky="w")

    def get(self):
        return bool(self.var.get())

class DateEditor(StringEditor):
    def get(self):
        v = super().get().strip()
        if v == "" or DATE_RE.match(v):
            return v
        # keep value, but warn once
        messagebox.showwarning("Date format", f"Date '{v}' should be YYYY-MM-DD")
        return v

# --------- Key/Value table for additionalProperties dicts ---------
class KeyValueTable(tk.Frame):
    """
    Editable table for {string_key: value}.
    - Backed by self._data so dict values are preserved (not stringified).
    - Inline add/edit; nested editor appears when value schema is an object.
    """
    def __init__(self, master, title="Items", value_dict=None, value_schema=None):
        super().__init__(master)
        self.value_schema = value_schema or {"type": "string"}
        self._data = copy.deepcopy(value_dict or {})
        self._nested = None

        ttk.Label(self, text=title).pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("key", "value"), show="headings", height=6)
        self.tree.heading("key", text="Key");    self.tree.column("key", width=220)
        self.tree.heading("value", text="Value");self.tree.column("value", width=240)
        self.tree.pack(fill="x", expand=False, pady=(2,4))

        btns = ttk.Frame(self); btns.pack(anchor="w", pady=(2,0))
        ttk.Button(btns, text="Add", command=lambda: self._start_edit(add=True)).pack(side="left", padx=2)
        ttk.Button(btns, text="Edit", command=lambda: self._start_edit(add=False)).pack(side="left", padx=2)
        ttk.Button(btns, text="Delete", command=self._del_row).pack(side="left", padx=2)

        # Inline editor
        self.inline = ttk.Frame(self); self.inline.pack(fill="x", pady=(6,0))
        ttk.Label(self.inline, text="Key:").grid(row=0, column=0, padx=(0,6), sticky="w")
        self.e_key = ttk.Entry(self.inline); self.e_key.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.inline, text="Value:").grid(row=0, column=2, padx=(12,6), sticky="w")
        self.e_value = ttk.Entry(self.inline); self.e_value.grid(row=0, column=3, sticky="ew")
        self.inline.columnconfigure(1, weight=1); self.inline.columnconfigure(3, weight=1)
        ttk.Button(self.inline, text="OK", command=self._save_edit).grid(row=0, column=4, padx=(12,2))
        ttk.Button(self.inline, text="Cancel", command=self._cancel_edit).grid(row=0, column=5)

        # Nested editor holder (for object values)
        self.nested_holder = ttk.Frame(self); self.nested_holder.pack(fill="x", pady=(6,0))

        self._editing_add = True
        self._editing_key = None
        self._refresh_tree()
        self._clear_inline()

    # ---- data <-> tree ----
    def _preview(self, v):
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, dict): return "{...}" if v else "{}"
        return str(v)

    def _refresh_tree(self):
        for r in self.tree.get_children(): self.tree.delete(r)
        for k, v in self._data.items():
            self.tree.insert("", "end", iid=k, values=(k, self._preview(v)))

    # ---- editing ----
    def _start_edit(self, add=True):
        self._editing_add = add
        self._editing_key = None
        self._clear_nested()

        if not add:
            sel = self.tree.selection()
            if not sel: return
            k = sel[0]
            self._editing_key = k
            v = self._data.get(k)
            self.e_key.delete(0, tk.END); self.e_key.insert(0, k)
            self.e_value.delete(0, tk.END)
            if not isinstance(v, dict): self.e_value.insert(0, self._preview(v))
        else:
            self.e_key.delete(0, tk.END); self.e_value.delete(0, tk.END)

        # If schema says object, open nested editor with the real dict
        if (self.value_schema or {}).get("type") == "object":
            existing = {}
            if self._editing_key:
                v = self._data.get(self._editing_key)
                existing = v if isinstance(v, dict) else {}
            sub_schema = (self.value_schema.get("additionalProperties")
                          if isinstance(self.value_schema.get("additionalProperties"), dict)
                          else {"type":"number"})
            ttk.Label(self.nested_holder, text="Nested items").pack(anchor="w")
            self._nested = KeyValueTable(self.nested_holder, title="", value_dict=existing, value_schema=sub_schema)
            self._nested.pack(fill="x")
        self.e_key.focus_set()

    def _save_edit(self):
        k = self.e_key.get().strip()
        if not k: return
        v = self._nested.get() if self._nested else self._parse_value(self.e_value.get())

        # Update backing store
        if not self._editing_add and self._editing_key and k != self._editing_key:
            # rename key
            self._data.pop(self._editing_key, None)
        self._data[k] = v

        self._refresh_tree()
        self._clear_inline()

    def _cancel_edit(self):
        self._clear_inline()

    def _del_row(self):
        for i in self.tree.selection():
            self._data.pop(i, None)
        self._refresh_tree()

    def _clear_inline(self):
        self.e_key.delete(0, tk.END); self.e_value.delete(0, tk.END)
        self._editing_add = True; self._editing_key = None
        self._clear_nested()

    def _clear_nested(self):
        for w in self.nested_holder.winfo_children(): w.destroy()
        self._nested = None

    # ---- parse scalars ----
    def _parse_value(self, s):
        n = _to_number(s)
        if n is not None:
            if isinstance(n, float) and n.is_integer(): n = int(n)
            return n
        b = _to_bool(s)
        if b is not None: return b
        return s

    # ---- API ----
    def get(self):
        return copy.deepcopy(self._data)

# --------- List editor for arrays ---------
class ArrayEditor(tk.Frame):
    """Generic array editor. If items are objects, it shows an inspector panel for the selected one."""
    def __init__(self, master, title="Items", value_list=None, item_schema=None):
        super().__init__(master)
        item_schema = item_schema or {"type": "string"}
        self.item_schema = item_schema
        ttk.Label(self, text=title).pack(anchor="w")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # left: listbox
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0,6))
        self.lb = tk.Listbox(left, height=7, exportselection=False)
        self.lb.pack(side="top", fill="y")
        btns = ttk.Frame(left)
        btns.pack(anchor="w", pady=(4,0))
        ttk.Button(btns, text="Add", command=self._add).pack(side="left", padx=2)
        ttk.Button(btns, text="Duplicate", command=self._dup).pack(side="left", padx=2)
        ttk.Button(btns, text="Delete", command=self._del).pack(side="left", padx=2)
        ttk.Button(btns, text="Up", command=lambda: self._move(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="Down", command=lambda: self._move(1)).pack(side="left", padx=2)

        # right: inspector
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self.inspector_holder = right

        self.items = []
        self._load(value_list or [])
        self.lb.bind("<<ListboxSelect>>", lambda e: self._refresh_inspector())

    def _load(self, arr):
        self.items = copy.deepcopy(arr)
        self.lb.delete(0, tk.END)
        for idx, it in enumerate(self.items):
            self.lb.insert(tk.END, self._label_for(it, idx))
        if self.items:
            self.lb.selection_set(0)
            self._refresh_inspector()

    def _label_for(self, it, idx):
        if isinstance(it, dict):
            # Prefer 'event', then 'description', then 'date'
            label = it.get("event") or it.get("description") or it.get("date")
            if label:
                return f"{idx:02d}: {label}"
        return f"{idx:02d}: {str(it)[:40]}"

    def _add(self):
        default = self._default_for(self.item_schema)
        self.items.append(default)
        self.lb.insert(tk.END, self._label_for(default, len(self.items)-1))
        self.lb.selection_clear(0, tk.END)
        self.lb.selection_set(tk.END)
        self._refresh_inspector()

    def _dup(self):
        sel = self._sel_index()
        if sel is None: return
        cp = copy.deepcopy(self.items[sel])
        self.items.insert(sel+1, cp)
        self._reload_labels()
        self.lb.selection_clear(0, tk.END)
        self.lb.selection_set(sel+1)
        self._refresh_inspector()

    def _del(self):
        sel = self._sel_index()
        if sel is None: return
        self.items.pop(sel)
        self._reload_labels()
        self._refresh_inspector()

    def _move(self, delta):
        sel = self._sel_index()
        if sel is None: return
        new = sel + delta
        if new < 0 or new >= len(self.items): return
        self.items[sel], self.items[new] = self.items[new], self.items[sel]
        self._reload_labels()
        self.lb.selection_clear(0, tk.END)
        self.lb.selection_set(new)
        self._refresh_inspector()

    def _reload_labels(self):
        self.lb.delete(0, tk.END)
        for idx, it in enumerate(self.items):
            self.lb.insert(tk.END, self._label_for(it, idx))

    def _sel_index(self):
        s = self.lb.curselection()
        return s[0] if s else None

    def _refresh_inspector(self):
        for w in self.inspector_holder.winfo_children():
            w.destroy()
        idx = self._sel_index()
        if idx is None:
            ttk.Label(self.inspector_holder, text="(no item selected)").pack(anchor="w")
            return

        it = self.items[idx]

        # Bold header with event/description/date
        if isinstance(it, dict):
            title_txt = it.get("event") or it.get("description") or it.get("date") or "Event"
            ttk.Label(self.inspector_holder, text=title_txt, font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0,6))

        editor = build_editor(self.inspector_holder, self.item_schema, it)
        editor.pack(fill="both", expand=True)

        def on_apply():
            self.items[idx] = editor.get_value()
            self._reload_labels()
            self.lb.selection_clear(0, tk.END)
            self.lb.selection_set(idx)

        ttk.Button(self.inspector_holder, text="Apply changes to item", command=on_apply).pack(anchor="e", pady=(6,0))

    def _default_for(self, schema):
        t = schema.get("type")
        if t == "object":
            out = {}
            for k, s in (schema.get("properties") or {}).items():
                out[k] = self._default_for(s)
            return out
        if t == "array":
            return []
        if "default" in schema:
            return copy.deepcopy(schema["default"])
        if t == "string":
            return ""
        if t in ("number", "integer"):
            return 0
        if t == "boolean":
            return False
        return None

    def get(self):
        # ensure current inspector writes back
        self._refresh_inspector()
        return copy.deepcopy(self.items)

# --------- Object editor ---------
class ObjectEditor(tk.Frame):
    def __init__(self, master, schema, value: dict):
        super().__init__(master)
        self.schema = schema
        self.value = copy.deepcopy(value) if isinstance(value, dict) else {}
        self._original_value = copy.deepcopy(self.value)
        self.widgets = {}

        props = schema.get("properties", {}) or {}
        row = 0
        if schema.get("title"):
            ttk.Label(
                self, text=schema["title"],
                font=("TkDefaultFont", 11, "bold")
            ).grid(row=row, column=0, sticky="w", pady=(0,4))
            row += 1

        for name, sub in props.items():
            init_val = self.value.get(name, self._default_for(sub))
            t = sub.get("type")

            if t in ("object", "array"):
                # Complex types get a labeled subframe; inside it we can pack freely.
                frame = ttk.Labelframe(self, text=name)
                frame.grid(row=row, column=0, sticky="ew", pady=4)
                self.columnconfigure(0, weight=1)

                editor = build_editor(frame, sub, init_val)  # no inline
                editor.pack(fill="both" if t == "array" else "x", expand=(t == "array"))
                self.widgets[name] = editor
            else:
                # Primitive editors are placed directly into this grid row.
                # build_editor returns a small frame (e.g., _Labeled) that manages
                # its internal widgets with grid, but we only grid *that frame*
                # into ObjectEditor (avoids mixing pack/grid in the same parent).
                editor = build_editor(self, sub, init_val)
                editor.grid(row=row, column=0, sticky="ew", pady=4)
                self.widgets[name] = editor

            row += 1

        # Handle additionalProperties (extras that aren’t in properties)
        addl = schema.get("additionalProperties")
        if addl:
            extras = {k: v for k, v in self.value.items() if k not in props}
            kv = KeyValueTable(self, title=schema.get("title","Items"),
                               value_dict=extras, value_schema=addl)
            kv.grid(row=row, column=0, sticky="ew", pady=4)
            self.widgets["_additional"] = kv

    def _default_for(self, schema):
        t = schema.get("type")
        if t == "object":
            out = {}
            for k, s in (schema.get("properties") or {}).items():
                out[k] = self._default_for(s)
            return out
        if t == "array":
            return []
        if "default" in schema:
            return copy.deepcopy(schema["default"])
        if t == "string":
            return ""
        if t in ("number", "integer"):
            return 0
        if t == "boolean":
            return False
        return None

def get_value(self):
    # Start from the original object so unknown keys are preserved
    out = copy.deepcopy(self._original_value)

    props = self.schema.get("properties", {}) or {}
    for name, sub in props.items():
        ed = self.widgets.get(name)
        if hasattr(ed, "get_value"):
            out[name] = ed.get_value()
        elif hasattr(ed, "get"):
            out[name] = ed.get()

    # If we had an "additionalProperties" table, overlay those edits
    if "_additional" in self.widgets:
        extras = self.widgets["_additional"].get()
        out.update(extras)

    return out

# --------- Builder ---------
def build_editor(master, schema, value, inline=False):
    t = schema.get("type")
    if t == "object":
        return ObjectEditor(master, schema, value or {})
    if t == "array":
        return ArrayEditor(master, title=schema.get("title","Items"), value_list=value or [], item_schema=schema.get("items") or {"type":"string"})
    if t in ("number", "integer"):
        cls = IntegerEditor if t == "integer" else NumberEditor
        return cls(master if inline else master, label=None if inline else schema.get("title"), value=value)
    if t == "boolean":
        return BoolEditor(master if inline else master, label=None if inline else schema.get("title"), value=value)
    if t == "string":
        if "enum" in schema:
            return EnumEditor(master if inline else master, label=None if inline else schema.get("title"), value=value, choices=tuple(schema["enum"]))
        if schema.get("format") == "date":
            return DateEditor(master if inline else master, label=None if inline else schema.get("title"), value=value)
        return StringEditor(master if inline else master, label=None if inline else schema.get("title"), value=value)
    # Fallback
    return StringEditor(master, label=schema.get("title"), value=str(value))

# --------- Scrollable editor frame (exported API) ---------
class JsonEditorFrame(ttk.Frame):
    """
    A scrollable container that renders a schema-driven editor for a given JSON object.
    Use .get_value() to retrieve the edited dict.
    """
    def __init__(self, master, data: dict, schema: dict):
        super().__init__(master)

        # Scrollable canvas
        canvas = tk.Canvas(self, highlightthickness=0)
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Inner frame that holds the actual editor
        self._inner = ttk.Frame(canvas)
        self._inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self._window = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        # --- Robust mouse-wheel scrolling (works on Linux/Wayland & Win/macOS) ---
        # Use bind_all so wheel events fire regardless of which child has the pointer.
        # Add guards + automatic unbind on destroy to avoid "invalid command name" errors.
        self._wheel_bindings = []

        def _y_scroll(steps):
            if canvas.winfo_exists():
                canvas.yview_scroll(steps, "units")

        def _on_mousewheel(event):
            # Windows/macOS: event.delta is +/-120 multiples
            delta = getattr(event, "delta", 0)
            if delta:
                steps = -int(delta / 120) or (-1 if delta < 0 else 1)
                _y_scroll(steps)

        def _on_btn4(event):  # X11/Wayland scroll up
            _y_scroll(-1)

        def _on_btn5(event):  # X11/Wayland scroll down
            _y_scroll(1)

        # Register global bindings (add="+": keep any existing app bindings)
        self.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        self.bind_all("<Button-4>", _on_btn4, add="+")   # many Linux setups
        self.bind_all("<Button-5>", _on_btn5, add="+")
        self._wheel_bindings.extend([
            ("<MouseWheel>", _on_mousewheel),
            ("<Button-4>", _on_btn4),
            ("<Button-5>", _on_btn5),
        ])

        # Ensure we clean up when this editor is destroyed
        def _cleanup(_):
            # remove only what we added (unbind_all removes all callbacks for that event)
            # which is acceptable here since we only ever add these in this module.
            for ev, _cb in self._wheel_bindings:
                self.unbind_all(ev)
            self._wheel_bindings.clear()

        self.bind("<Destroy>", _cleanup)

        # Resize handler to make content width follow the frame
        def _on_resize(event):
            canvas.itemconfig(self._window, width=event.width)
        canvas.bind("<Configure>", _on_resize)

        # Build the actual editor
        self._root_editor = build_editor(self._inner, schema, data)
        self._root_editor.pack(fill="both", expand=True, padx=8, pady=8)

    def get_value(self):
        ed = self._root_editor
        if hasattr(ed, "get_value"):
            val = ed.get_value()
        elif hasattr(ed, "get"):
            val = ed.get()
        else:
            val = None
        # Basic sanity
        if isinstance(val, dict) and val:
            return val
        # If we somehow got here, refuse to hand back {} — let the GUI guard handle it.
        return {}

# --------- Default schemas (you can import & tweak) ---------
USER_SCHEMA_GUESS = {
    "type": "object",
    "title": "User",
    "properties": {
        # required top-level ages
        "current_age": {"type":"integer", "title":"Current age"},
        "stop_age": {"type":"integer", "title":"Stop age"},

        # optional grouping for person metadata (kept from before)
        "person": {
            "type": "object",
            "title": "Person",
            "properties": {
                "name": {"type":"string", "title":"Name"},
                "age": {"type":"integer", "title":"Age"},
                "retirement_date": {"type":"string", "format":"date", "title":"Retirement date"}
            }
        },

        "income": {
            "type":"object",
            "title":"Income",
            "additionalProperties": {"type":"number"}
        },

        "expenses": {
            "type":"object",
            "title":"Expenses",
            "properties": {
                "total_tax_rate": {"type":"number", "title":"Total tax rate"},
                "spending_policy": {
                    "type": "object",
                    "title": "Spending policy",
                    "properties": {
                        "type": {"type": "string", "title": "Policy type"},
                        "cap_rate": {"type": "number", "title": "Cap rate (annual)"},
                        "priority_order": {
                            "type": "array",
                            "title": "Priority order (cut list)",
                            "items": {"type": "string"}
                        }
                    },
                    "additionalProperties": {"type": "number"}
                },
                "classification": {
                    "type": "object",
                    "title": "Classification",
                    "additionalProperties": {
                        "type": "string",
                        "enum": ["fixed", "discretionary"]
                    }
                },
                "breakdown": {
                    "type":"object",
                    "title":"Breakdown",
                    "additionalProperties": {"type":"number"}
                }
            },
            "additionalProperties": {"type":"number"}
        },

        "portfolio": {
            "type":"object",
            "title":"Portfolio",
            "properties": {
                "breakdown": {
                    "type":"object",
                    "title":"Breakdown",
                    "additionalProperties": {
                        "type": "object",
                        "additionalProperties": {"type":"number"}
                    }
                }
            },
            "additionalProperties": {"type":"number"}
        }
    }
}

SCENARIO_SCHEMA_GUESS = {
    "type":"object",
    "title":"Scenario",
    "properties": {
        "description": {"type":"string", "title":"Description"},
        "assumptions": {
            "type":"object",
            "title":"Assumptions",
            "properties": {
                "expected_return": {"type":"number", "title":"Expected return"},
                "variance": {"type":"number", "title":"Variance"},
                "inflation": {"type":"number", "title":"Inflation"}
            }
        },
        "life_events": {
            "type":"array",
            "title":"Life events",
            "items": {
                "type":"object",
                "title":"Event",
                "properties": {
                    "event": {"type":"string", "title":"Event name"},
                    "date": {"type":"string", "format":"date", "title":"Date"},
                    "description": {"type":"string", "title":"Description"},
                    "updated_income": {
                        "type":"object",
                        "title":"Updated income",
                        "additionalProperties": {"type":"number"}
                    },
                    "updated_expenses": {
                        "type":"object",
                        "title":"Updated expenses",
                        "properties": {
                            "total_tax_rate": {"type":"number", "title":"Total tax rate"},
                            "breakdown": {
                                "type":"object",
                                "title":"Breakdown",
                                "additionalProperties": {"type":"number"}
                            }
                        },
                        "additionalProperties": {"type":"number"}
                    },
                    # Keep 'changes' for backward-compat (free-form), numeric by default
                    "changes": {
                        "type":"object",
                        "title":"Changes",
                        "additionalProperties": {"type":"number"}
                    }
                }
            }
        }
    }
}
