"""Editable template selection with suggestions that leave focus in the entry."""

import tkinter as tk
from tkinter import ttk


class TemplateSelector(ttk.Combobox):
    def __init__(self, parent, choices, selected, on_select, **kwargs):
        self.query = tk.StringVar(master=parent, value=selected)
        super().__init__(parent, values=choices, textvariable=self.query, **kwargs)
        self.choices = tuple(choices)
        self.selected = selected
        self.on_select = on_select
        self._setting_selection = False

        window = self.winfo_toplevel()
        self.popup = tk.Frame(window, bg="#3D566B", padx=1, pady=1)
        self.popup.columnconfigure(0, weight=1)
        self.suggestions = tk.Listbox(
            self.popup, bg="#1A2634", fg="#F0F5FA", selectbackground="#334B61",
            selectforeground="#F0F5FA", font=self.cget("font"), activestyle="none",
            highlightthickness=0, borderwidth=0, exportselection=False, takefocus=False,
        )
        self.suggestions.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self.popup, orient="vertical", command=self.suggestions.yview)
        self.suggestions.configure(yscrollcommand=self.scrollbar.set)

        self.query.trace_add("write", self._on_edit)
        self.bind("<ButtonPress-1>", self._on_entry_click)
        self.bind("<Down>", lambda _event: self._move(1))
        self.bind("<Up>", lambda _event: self._move(-1))
        self.bind("<Return>", self._confirm)
        self.bind("<Escape>", self._cancel)
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<FocusOut>", self._hide)
        self.bind("<<ComboboxSelected>>", self._confirm)
        self.suggestions.bind("<ButtonPress-1>", self._on_result_click)
        window.bind("<ButtonPress-1>", self._on_window_click, add="+")

    def replace_choices(self, choices, selected):
        self.choices = tuple(choices)
        self._set_selection(selected)

    def _set_selection(self, name):
        self._hide()
        self.selected = name
        self._setting_selection = True
        try:
            self.set(name)
        finally:
            self._setting_selection = False
        self.configure(values=self.choices)

    def _on_edit(self, *_):
        if not self._setting_selection and self.focus_get() == self:
            self._show(self.query.get())

    def _on_focus(self, _event):
        if self.get() == self.selected:
            self.selection_range(0, "end")

    def _show(self, text):
        query = text.strip().casefold()
        matches = [name for name in self.choices if query in name.casefold()]
        self.configure(values=matches)
        if not matches:
            self._hide()
            return

        self.suggestions.delete(0, "end")
        self.suggestions.insert("end", *matches)
        self.suggestions.configure(height=min(8, len(matches)))
        if len(matches) > 8:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar.grid_remove()
        selected = self.query.get().strip()
        index = matches.index(selected) if selected in matches else 0
        self._highlight(index)
        self.popup.place(in_=self, rely=1, relwidth=1)
        self.popup.lift()

    def _hide(self, _event=None):
        self.popup.place_forget()

    def _is_open(self):
        return self.popup.winfo_manager() == "place"

    def _on_entry_click(self, event):
        if not self.identify(event.x, event.y).endswith("downarrow"):
            return None
        self.focus_set()
        if self._is_open():
            self._hide()
        else:
            self._show("" if self.get() == self.selected else self.get())
        return "break"

    def _on_window_click(self, event):
        if event.widget not in (self, self.popup, self.suggestions, self.scrollbar):
            self._hide()

    def _highlight(self, index):
        self.suggestions.selection_clear(0, "end")
        self.suggestions.selection_set(index)
        self.suggestions.see(index)

    def _move(self, direction):
        if not self._is_open():
            self._show("" if self.get() == self.selected else self.get())
        else:
            selection = self.suggestions.curselection()
            current = selection[0] if selection else 0
            index = max(0, min(self.suggestions.size() - 1, current + direction))
            self._highlight(index)
        return "break"

    def _confirm(self, _event):
        selection = self.suggestions.curselection() if self._is_open() else ()
        entered = self.get().strip()
        if selection:
            self._choose(self.suggestions.get(selection[0]))
        elif entered in self.choices:
            self._choose(entered)
        else:
            self._set_selection(self.selected)
        return "break"

    def _cancel(self, _event):
        self._set_selection(self.selected)
        return "break"

    def _on_result_click(self, event):
        index = self.suggestions.nearest(event.y)
        self._choose(self.suggestions.get(index))
        return "break"

    def _choose(self, name):
        self._set_selection(name)
        self.on_select(name)
