"""Contact Sheet: a local, open-source culling and captioning desktop app."""
from __future__ import annotations
import csv
import json
import queue
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from PIL import ImageTk
from renaming import capture_date, rename_plan, apply_rename
from delivery import Destination, upload_files
from iptc import GROUPS, FIELDS, STRUCTURE_HINTS
from selection import PhotoSelection
from editors import saved_editor, remember_editor, open_in_editor, named_editor
from core import photos, preview, load_metadata, save_metadata, export_photos, empty_metadata

class ContactSheet(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Contact Sheet 0.3.0 — Cull • Caption • Edit')
        self.geometry('1380x860')
        self.minsize(1000, 680)
        self.configure(bg='#d4d4d4')
        self.paths = []
        self.visible = []
        self.selection = PhotoSelection()
        self.editor = saved_editor()
        self.metadata = {}
        self.capture_dates = {}
        self.errors = {}
        self.current = None
        self.folder = None
        self.dirty = False
        self.generation = 0
        self.preview_token = 0
        self.results = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.preview_pool = ThreadPoolExecutor(max_workers=1)
        self.preview_future = None
        self.cache = OrderedDict()
        self.pending = set()
        self.page = 0
        self.page_size = 12
        self.mode = 'fit'
        self.photo_refs = []
        self.filter = tk.StringVar(value='All photos')
        self.search = tk.StringVar()
        self.status = tk.StringVar(value='Open a folder to begin. Photos stay on your computer.')
        icon_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'assets'/'contact-sheet.png'
        if icon_path.exists():
            self.app_icon = ImageTk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self.app_icon)
        self._build()
        self._bind_shortcuts()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(70, self._poll)

    def _build(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#cccccc', foreground='#202020', fieldbackground='#f6f6f6')
        style.configure('TButton', padding=(8, 6))
        style.map('TButton', background=[('active', '#bcbcbc')])
        style.configure('Treeview', background='#f6f6f6', fieldbackground='#f6f6f6', foreground='#202020')
        style.configure('TEntry', fieldbackground='#f6f6f6')
        style.configure('TCombobox', fieldbackground='#f6f6f6')
        bar = ttk.Frame(self, padding=12)
        bar.pack(fill='x')
        ttk.Label(bar, text='CONTACT SHEET', font=('Helvetica', 17, 'bold')).pack(side='left', padx=(0, 18))
        ttk.Button(bar, text='Open folder', command=self.open_folder).pack(side='left')
        ttk.Button(bar, text='Rename selected…', command=self.rename_selected).pack(side='left', padx=6)
        ttk.Button(bar, text='Export picks', command=self.export).pack(side='left')
        ttk.Button(bar, text='Upload selected…', command=self.upload_selected).pack(side='left', padx=6)
        editor_button = ttk.Menubutton(bar, text='Open in…')
        editor_menu = tk.Menu(editor_button, tearoff=False)
        editor_menu.add_command(label='Photoshop', command=lambda: self.open_selected_in_editor('Photoshop'))
        editor_menu.add_command(label='Photo Craft', command=lambda: self.open_selected_in_editor('Photo Craft'))
        editor_menu.add_separator()
        editor_menu.add_command(label='Other editor…', command=self.open_selected_in_editor)
        editor_button.configure(menu=editor_menu)
        editor_button.pack(side='left', padx=6)
        ttk.Button(bar, text='Caption CSV', command=self.csv_export).pack(side='left')
        ttk.Button(bar, text='Shortcuts', command=self.help).pack(side='right')
        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, padding=10)
        center = ttk.Frame(body, padding=10)
        right = ttk.Frame(body, padding=14, width=290)
        body.add(left, weight=3)
        body.add(center, weight=5)
        body.add(right, weight=2)
        self.folder_label = ttk.Label(left, text='No folder open', wraplength=340)
        self.folder_label.pack(anchor='w', pady=(0, 8))
        combo = ttk.Combobox(left, textvariable=self.filter, state='readonly', values=['All photos', 'Picks', 'Unrated', 'Rejected', '1+ stars', '2+ stars', '3+ stars', '4+ stars', '5 stars'])
        combo.pack(fill='x')
        combo.bind('<<ComboboxSelected>>', lambda e: self.filter_photos())
        entry = ttk.Entry(left, textvariable=self.search)
        entry.pack(fill='x', pady=7)
        self.search.trace_add('write', lambda *args: self.filter_photos())
        ttk.Label(left, text='Search filenames, captions, keywords', font=('Helvetica', 10)).pack(anchor='w')
        selection_bar = ttk.Frame(left)
        selection_bar.pack(fill='x', pady=(8, 0))
        ttk.Button(selection_bar, text='Select all', command=self.select_all).pack(side='left')
        ttk.Button(selection_bar, text='Clear', command=self.clear_selection).pack(side='left', padx=5)
        self.selection_count = ttk.Label(selection_bar, text='0 selected')
        self.selection_count.pack(side='right')
        self.grid = ttk.Frame(left)
        self.grid.pack(fill='both', expand=True, pady=8)
        nav = ttk.Frame(left)
        nav.pack(fill='x')
        ttk.Button(nav, text='‹ Page', command=lambda: self.change_page(-1)).pack(side='left')
        self.page_label = ttk.Label(nav)
        self.page_label.pack(side='left', padx=8)
        ttk.Button(nav, text='Page ›', command=lambda: self.change_page(1)).pack(side='right')
        self.filename = ttk.Label(center, text='Choose a photo', font=('Helvetica', 13, 'bold'))
        self.filename.pack(anchor='w', pady=(0, 8))
        self.capture_label = ttk.Label(center, text='Date captured: —')
        self.capture_label.pack(anchor='w', pady=(0,8))
        self.canvas = tk.Canvas(center, background='#a8a8a8', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        controls = ttk.Frame(center)
        controls.pack(fill='x', pady=8)
        ttk.Button(controls, text='← Previous', command=lambda: self.move(-1)).pack(side='left')
        ttk.Button(controls, text='Next →', command=lambda: self.move(1)).pack(side='left', padx=6)
        ttk.Button(controls, text='Fit / 100%', command=self.toggle_zoom).pack(side='right')
        self.rating_text = ttk.Label(center, text='0–5: stars   P: pick   X: reject   U: clear   Z: zoom')
        self.rating_text.pack(anchor='w')
        ttk.Label(right, text='CAPTION & METADATA', font=('Helvetica', 12, 'bold')).pack(anchor='w')
        ttk.Button(right, text='Edit IPTC fields…', command=self.edit_iptc).pack(fill='x', pady=8)
        ttk.Label(right, text='Description / caption').pack(anchor='w')
        self.caption = tk.Text(right, height=9, width=29, wrap='word', bg='#f6f6f6', fg='#202020', undo=True)
        self.caption.pack(fill='x')
        self.caption.bind('<<Modified>>', self.modified)
        self.fields = {}
        for name, title in [('creator','Photographer / byline'), ('copyright','Copyright'), ('keywords','Keywords (comma-separated)')]:
            ttk.Label(right, text=title, padding=(0,12,0,4)).pack(anchor='w')
            variable = tk.StringVar()
            ttk.Entry(right,textvariable=variable).pack(fill='x')
            variable.trace_add('write',lambda *a: self.mark_dirty())
            self.fields[name] = variable
        ttk.Button(right, text='Save caption  ⌘/Ctrl+S', command=self.save).pack(fill='x', pady=(18, 8))
        ttk.Button(right, text='Apply these fields to picks…', command=self.batch_caption).pack(fill='x')
        self.editor_label = ttk.Label(right, text=self.editor.name if self.editor else 'Choose an editor with Open in app', wraplength=260)
        self.editor_label.pack(anchor='w', pady=(12, 4))
        ttk.Button(right, text='Change editor…', command=self.choose_editor).pack(fill='x')
        ttk.Label(right, text='Metadata saves to XMP sidecars.\nOriginal photos are never rewritten.\n\nPick = green label; reject = −1 rating.\nRename selected previews new names.\nExport picks copies marked photos.\nOpen in app sends selected originals.', wraplength=260, padding=(0, 16, 0, 0)).pack(anchor='w')
        ttk.Label(self, textvariable=self.status, padding=8).pack(fill='x')

    def edit_iptc(self):
        if self.current is None:
            messagebox.showinfo('Choose a photo', 'Open a folder and select a photo first.'); return
        if not self.save(): return
        dialog = tk.Toplevel(self)
        dialog.title('IPTC metadata — ' + self.current.name)
        dialog.geometry('900x720')
        dialog.transient(self)
        dialog.grab_set()
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill='both', expand=True, padx=12,pady=12)
        variables = {}
        for group, fields in GROUPS.items():
            tab = ttk.Frame(notebook); notebook.add(tab,text=group)
            canvas = tk.Canvas(tab,bg='#cccccc',highlightthickness=0)
            scrollbar = ttk.Scrollbar(tab,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
            form = ttk.Frame(canvas,padding=14)
            window = canvas.create_window(0,0,window=form,anchor='nw')
            form.bind('<Configure>',lambda e,c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda e,c=canvas,w=window: c.itemconfigure(w,width=e.width))
            ttk.Label(form,text='Lists: separate values with semicolons. Use Edit rows for repeated entries.',wraplength=750).pack(anchor='w',pady=(0,10))
            for key,title,prefix,prop,kind in fields:
                ttk.Label(form,text=title).pack(anchor='w',pady=(10,3))
                value = self.metadata[self.current].get(key,'')
                if key == 'keywords': value = '; '.join(value)
                variable = tk.StringVar(value=value); variables[key] = variable
                ttk.Entry(form,textvariable=variable).pack(fill='x')
                if kind == 'json':
                    ttk.Button(form,text='Edit rows…',command=lambda k=key,v=variable: self.edit_metadata_rows(dialog,k,v)).pack(anchor='w',pady=4)
        footer = ttk.Frame(dialog,padding=12); footer.pack(fill='x')
        def commit():
            data = dict(self.metadata[self.current])
            for key,var in variables.items():
                data[key] = [x.strip() for x in var.get().split(';') if x.strip()] if key == 'keywords' else var.get()
            try: save_metadata(self.current,data)
            except Exception as exc:
                messagebox.showerror('Could not save metadata',str(exc),parent=dialog); return
            self.metadata[self.current] = data
            for name,var in self.fields.items(): var.set(', '.join(data[name]) if name == 'keywords' else data[name])
            self.dirty = False
            self.status.set('Saved IPTC metadata for '+self.current.name)
            dialog.destroy()
        ttk.Button(footer,text='Save metadata',command=commit).pack(side='right')
        ttk.Button(footer,text='Cancel',command=dialog.destroy).pack(side='right',padx=8)

    def edit_metadata_rows(self, parent, key, variable):
        try:
            rows = json.loads(variable.get() or '[]')
            if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows): raise ValueError('Expected a list of entries.')
        except ValueError as exc:
            messagebox.showerror('Invalid entries',str(exc),parent=parent); return
        window = tk.Toplevel(parent)
        window.title(FIELDS[key][1]); window.geometry('750x600'); window.transient(parent); window.grab_set()
        columns = [c.strip() for c in STRUCTURE_HINTS[key].split(',')]
        listbox = tk.Listbox(window,height=7); listbox.pack(fill='x',padx=12,pady=10)
        form = ttk.Frame(window,padding=12); form.pack(fill='both',expand=True)
        entries = {}
        for column in columns:
            ttk.Label(form,text=column).pack(anchor='w')
            var=tk.StringVar(); entries[column]=var
            ttk.Entry(form,textvariable=var).pack(fill='x',pady=(0,5))
        selected = [None]
        def refresh():
            listbox.delete(0,'end')
            for i,row in enumerate(rows): listbox.insert('end',str(i+1)+': '+str(next(iter(row.values()),'Empty entry')))
        def store_row():
            index=selected[0]
            if index is None: return
            for column,var in entries.items():
                value=var.get()
                if isinstance(rows[index].get(column),list): value=[x.strip() for x in value.split(';') if x.strip()]
                if value: rows[index][column]=value
                else: rows[index].pop(column,None)
        def select(event=None):
            choice=listbox.curselection()
            if not choice: return
            store_row(); selected[0]=choice[0]
            for column,var in entries.items():
                value=rows[selected[0]].get(column,'')
                var.set('; '.join(value) if isinstance(value,list) else value)
        def add():
            store_row(); rows.append({}); selected[0]=len(rows)-1; refresh()
            listbox.selection_set(selected[0])
            for var in entries.values(): var.set('')
        def remove():
            if selected[0] is not None: rows.pop(selected[0]); selected[0]=None
            refresh()
            for var in entries.values(): var.set('')
        def done():
            store_row(); variable.set(json.dumps(rows,ensure_ascii=False) if rows else '')
            window.destroy(); parent.grab_set()
        listbox.bind('<<ListboxSelect>>',select)
        buttons=ttk.Frame(window,padding=12); buttons.pack(fill='x')
        ttk.Button(buttons,text='Add',command=add).pack(side='left')
        ttk.Button(buttons,text='Remove',command=remove).pack(side='left',padx=6)
        ttk.Button(buttons,text='Use entries',command=done).pack(side='right')
        refresh()
        if rows: listbox.selection_set(0); select()

    def _bind_shortcuts(self):
        for key, action in [('<Left>', lambda: self.move(-1)), ('<Right>', lambda: self.move(1)), ('<p>', lambda: self.rate(label='Green')), ('<x>', lambda: self.rate(-1, '')), ('<u>', lambda: self.rate(0, '')), ('<z>', self.toggle_zoom)]:
            self.bind(key, lambda e, fn=action: self.shortcut(e, fn))
        for n in range(6):
            self.bind(str(n), lambda e, rating=n: self.shortcut(e, lambda: self.rate(rating)))
        for modifier in ('Control', 'Command'):
            try:
                self.bind(f'<{modifier}-s>', lambda e: self.save())
                self.bind(f'<{modifier}-o>', lambda e: self.open_folder())
                self.bind(f'<{modifier}-a>', lambda e: self.shortcut(e, self.select_all))
            except tk.TclError:
                pass
        self.bind('<Escape>', lambda e: self.shortcut(e, self.clear_selection))
    def shortcut(self, event, action):
        if isinstance(self.focus_get(), (tk.Text, ttk.Entry, ttk.Combobox)):
            return
        action()
        return 'break'
    def modified(self, event=None):
        if self.caption.edit_modified():
            self.mark_dirty()
            self.caption.edit_modified(False)
    def mark_dirty(self):
        if self.current is not None:
            self.dirty = True
    def data(self):
        result = dict(self.metadata[self.current])
        result['caption'] = self.caption.get('1.0', 'end-1c')
        for name in ['creator', 'copyright']:
            result[name] = self.fields[name].get()
        result['keywords'] = list(dict.fromkeys(w.strip() for w in self.fields['keywords'].get().split(',') if w.strip()))
        return result
    def save(self):
        if self.current is None or not self.dirty:
            return True
        if self.current in self.errors:
            messagebox.showerror('Metadata needs attention', self.errors[self.current])
            return False
        try:
            data = self.data()
            save_metadata(self.current, data)
            self.metadata[self.current] = data
            self.dirty = False
            self.status.set(f'Saved {self.current.name}.xmp')
            return True
        except Exception as exc:
            messagebox.showerror('Could not save metadata', str(exc))
            return False
    def open_folder(self):
        if not self.save():
            return
        folder = filedialog.askdirectory(title='Open a photo folder or memory card')
        if not folder:
            return
        self.generation += 1
        generation = self.generation
        self.folder_label.config(text=folder)
        self.status.set('Reading folder and metadata…')
        def load():
            try:
                paths = photos(folder)
                data, errors = {}, {}
                for path in paths:
                    try:
                        data[path] = load_metadata(path)
                    except Exception as exc:
                        data[path] = empty_metadata()
                        errors[path] = f'{path.name}: {exc}. Existing metadata has been left untouched.'
                self.results.put(('folder', generation, (folder, paths, data, errors)))
            except Exception as exc:
                self.results.put(('error', generation, str(exc)))
        self.pool.submit(load)
    def filter_photos(self):
        query = self.search.get().casefold().strip()
        mode = self.filter.get()
        def matches(path):
            data = self.metadata[path]
            rating = data['rating']
            if mode == 'Picks' and data['label'] != 'Green': return False
            if mode == 'Unrated' and rating != 0: return False
            if mode == 'Rejected' and rating != -1: return False
            if 'stars' in mode and rating < int(mode[0]): return False
            return query in (path.name + ' ' + data['caption'] + ' ' + ' '.join(data['keywords'])).casefold()
        self.visible = [p for p in self.paths if matches(p)]
        self.selection.retain_visible(self.visible)
        self.page = 0
        self.render_grid()
    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.visible)-1)//self.page_size), self.page + delta))
        self.render_grid()
    def request_preview(self, path, size, purpose, token=None, full=False):
        key = (path, size, full)
        if purpose == 'thumb' and key in self.pending:
            return
        if purpose == 'thumb': self.pending.add(key)
        generation = self.generation
        def work():
            try:
                value = preview(path, size, full)
            except Exception as exc:
                value = str(exc)
            self.results.put((purpose, generation, (key, token, value)))
        if purpose == "preview":
            if self.preview_future is not None:
                self.preview_future.cancel()
            self.preview_future = self.preview_pool.submit(work)
        else:
            self.pool.submit(work)
    def render_grid(self):
        for child in self.grid.winfo_children(): child.destroy()
        self.photo_refs = []
        self.thumb_widgets = {}
        start = self.page*self.page_size
        for i, path in enumerate(self.visible[start:start+self.page_size]):
            row, col = divmod(i, 3)
            selected = path in self.selection.selected
            box = tk.Frame(self.grid, bg='#b4cee5' if selected else '#d4d4d4', padx=4, pady=4, highlightthickness=2, highlightbackground='#357bad' if path == self.current else ('#588caf' if selected else '#d4d4d4'))
            box.grid(row=row, column=col, sticky='nsew', padx=2, pady=2)
            button = tk.Label(box, text='Loading…', bg='#d4d4d4', fg='#202020', width=14, height=4)
            button.pack(fill='both', expand=True)
            self.bind_photo_click(button, path)
            self.bind_photo_click(box, path)
            data = self.metadata[path]
            symbol = 'REJECT' if data['rating'] == -1 else '★'*data['rating']
            if data['label'] == 'Green': symbol = 'PICK ' + symbol
            label = tk.Label(box, text=path.name[:18]+'\n'+symbol, bg=box['bg'], fg='#246b36' if data['label']=='Green' else '#252525', font=('Helvetica', 9))
            label.pack()
            self.bind_photo_click(label, path)
            self.thumb_widgets[path] = button
            key = (path, (140, 85), False)
            if key in self.cache: self.set_thumb(path, self.cache[key])
            else: self.request_preview(path, (140, 85), 'thumb')
        for col in range(3): self.grid.columnconfigure(col, weight=1)
        self.selection_count.config(text=f'{len(self.selection.selected)} selected')
        self.page_label.config(text=f'{self.page+1} / {max(1, (len(self.visible)+self.page_size-1)//self.page_size)} · {len(self.visible)} photos')
    def set_thumb(self, path, value):
        widget = self.thumb_widgets.get(path)
        if widget is None: return
        if isinstance(value, str):
            widget.config(text='No preview', height=4)
        else:
            photo = ImageTk.PhotoImage(value)
            self.photo_refs.append(photo)
            widget.config(image=photo, text='', width=0, height=0)
    def bind_photo_click(self, widget, path):
        widget.bind('<Button-1>', lambda e: self.select(path))
        widget.bind('<Shift-Button-1>', lambda e: self.select(path, extend=True))
        modifier = 'Command' if sys.platform == 'darwin' else 'Control'
        widget.bind(f'<{modifier}-Button-1>', lambda e: self.select(path, toggle=True))
        widget.bind(f'<{modifier}-Shift-Button-1>', lambda e: self.select(path, toggle=True, extend=True))

    def selected_paths(self):
        return self.selection.ordered(self.visible)

    def select_all(self):
        if not self.save(): return
        self.selection.select_all(self.visible)
        self.render_grid()
        self.status.set(f'{len(self.selection.selected)} photos selected across all filtered pages.')

    def clear_selection(self):
        self.selection.clear()
        self.render_grid()
        self.status.set('Selection cleared.')

    def select(self, path, toggle=False, extend=False):
        if path not in self.visible or not self.save(): return
        self.selection.click(path, self.visible, toggle=toggle, extend=extend)
        self.current = path
        data = self.metadata[path]
        self.caption.delete('1.0', 'end')
        self.caption.insert('1.0', data['caption'])
        self.caption.edit_modified(False)
        for name, var in self.fields.items(): var.set(', '.join(data[name]) if name=='keywords' else data[name])
        self.dirty = False
        self.filename.config(text=path.name)
        if path not in self.capture_dates: self.capture_dates[path] = capture_date(path)
        date = self.capture_dates[path]
        self.capture_label.config(text='Date captured: ' + (date.strftime('%Y-%m-%d %H:%M:%S') if date else 'Unavailable'))
        if path in self.visible: self.page = self.visible.index(path)//self.page_size
        self.render_grid()
        self.show_preview()
        self.focus_set()
        self.status.set(self.errors[path] if path in self.errors else f'{len(self.selection.selected)} selected · Cmd/Ctrl-click to add, Shift-click for a range')
    def move(self, delta):
        if not self.visible: return
        index = self.visible.index(self.current) if self.current in self.visible else (-1 if delta>0 else len(self.visible))
        self.select(self.visible[max(0, min(len(self.visible)-1, index+delta))])
    def rate(self, rating=None, label=None):
        if self.current is None or not self.save(): return
        old = self.metadata[self.current]
        data = dict(old)
        if rating is not None: data['rating'] = rating
        if label is not None:
            data['label'] = label
            if label == 'Green' and data['rating'] == -1: data['rating'] = 0
        try:
            if self.current in self.errors: raise ValueError(self.errors[self.current])
            save_metadata(self.current, data)
            self.metadata[self.current] = data
            self.status.set(f'{self.current.name}: rating {data["rating"]}, label {data["label"] or "none"}')
            self.filter_photos()
            if self.current in self.visible:
                self.page = self.visible.index(self.current)//self.page_size
                self.render_grid()
        except Exception as exc: messagebox.showerror('Could not rate photo', str(exc))
    def show_preview(self):
        if self.current is None: return
        self.preview_token += 1
        self.canvas.delete('all')
        self.canvas.create_text(20, 20, anchor='nw', fill='#202020', text='Loading preview…')
        size = (max(500, self.canvas.winfo_width()), max(400, self.canvas.winfo_height()))
        self.request_preview(self.current, size, 'preview', self.preview_token, self.mode=='100%')
    def toggle_zoom(self):
        self.mode = '100%' if self.mode=='fit' else 'fit'
        self.status.set('100% · drag to pan (RAW uses embedded preview)' if self.mode=='100%' else 'Fit preview')
        self.show_preview()
    def _poll(self):
        try:
            while True:
                kind, generation, payload = self.results.get_nowait()
                if generation != self.generation and kind not in ('export', 'export_error', 'editor', 'editor_error'):
                    if kind == 'thumb': self.pending.discard(payload[0])
                    continue
                if kind == 'folder':
                    if not self.save(): continue
                    self.folder, self.paths, self.metadata, self.errors = payload
                    self.current = None
                    self.selection.clear()
                    self.preview_token += 1
                    self.cache.clear()
                    self.pending.clear()
                    self.search.set('')
                    self.filter.set('All photos')
                    self.filter_photos()
                    self.status.set(f'{len(self.paths)} photos · {len(self.errors)} metadata warnings')
                    if self.paths: self.select(self.paths[0])
                    else:
                        self.canvas.delete('all')
                        self.filename.config(text='No supported photos in this folder')
                        self.caption.delete('1.0', 'end')
                elif kind == 'renamed':
                    mapping, dialog = payload
                    self.generation += 1
                    self.preview_token += 1
                    current = mapping.get(self.current,self.current)
                    self.paths = sorted([mapping.get(p,p) for p in self.paths],key=lambda p:p.name.casefold())
                    self.metadata = {mapping.get(p,p):d for p,d in self.metadata.items()}
                    self.capture_dates = {mapping.get(p,p):d for p,d in self.capture_dates.items()}
                    self.errors = {mapping.get(p,p):d for p,d in self.errors.items()}
                    selected = {mapping.get(p,p) for p in self.selection.selected}
                    self.selection.anchor = mapping.get(self.selection.anchor,self.selection.anchor)
                    self.selection.selected = selected
                    self.current = None
                    self.cache.clear(); self.pending.clear()
                    self.filter_photos()
                    if current in self.visible: self.select(current)
                    self.selection.selected = selected.intersection(self.visible); self.render_grid()
                    dialog.destroy()
                    self.status.set(f'Renamed {len(mapping)} photos and their sidecars.')
                elif kind == 'rename_error':
                    error,dialog = payload; dialog.destroy()
                    messagebox.showerror('Rename stopped',error)
                elif kind == 'error': messagebox.showerror('Operation failed', payload)
                elif kind == 'editor': self.status.set(payload)
                elif kind == 'editor_error': messagebox.showerror('Could not open editor', payload)
                elif kind == 'export_error': messagebox.showerror('Export stopped', payload)
                elif kind == 'export':
                    self.status.set(payload)
                    messagebox.showinfo('Export complete', payload)
                elif kind == 'thumb':
                    key, token, value = payload
                    self.pending.discard(key)
                    self.cache[key] = value
                    while len(self.cache)>180: self.cache.popitem(last=False)
                    self.set_thumb(key[0], value)
                elif kind == 'preview':
                    key, token, value = payload
                    if token != self.preview_token or key[0]!=self.current: continue
                    self.canvas.delete('all')
                    if isinstance(value, str):
                        self.canvas.create_text(20, 20, anchor='nw', fill='#202020', width=440, text=value)
                    else:
                        self.preview_ref = ImageTk.PhotoImage(value)
                        self.canvas.create_image(0, 0, anchor='nw', image=self.preview_ref)
                        self.canvas.configure(scrollregion=(0, 0, value.width, value.height))
                        self.canvas.xview_moveto(0)
                        self.canvas.yview_moveto(0)
        except queue.Empty: pass
        self.after(70, self._poll)
    def picks(self):
        return [p for p in self.paths if self.metadata[p]['label']=='Green' and self.metadata[p]['rating']>=0]
    def export(self):
        if not self.save(): return
        self.copy_export(self.picks(), 'picks')

    def copy_export(self, paths, description):
        if any(p in self.errors for p in paths):
            messagebox.showerror('Metadata needs attention', 'One or more photos has unreadable metadata. Resolve the sidecar error before exporting.'); return
        if not paths:
            messagebox.showinfo('No photos', 'Select photos with Cmd/Ctrl-click or Shift-click, or mark picks with P.'); return
        folder = filedialog.askdirectory(title=f'Copy {len(paths)} {description} to an empty destination folder')
        if not folder: return
        self.status.set(f'Copying {len(paths)} {description}…')
        generation = self.generation
        def work():
            try:
                count = export_photos(paths, folder)
                self.results.put(('export', generation, f'Copied {count} photos and available sidecars.'))
            except Exception as exc:
                self.results.put(('export_error', generation, 'Some files may have been copied before stopping. ' + str(exc)))
        self.pool.submit(work)

    def choose_editor(self, name=None):
        if sys.platform == 'darwin':
            options = dict(title='Choose Photoshop or another photo editor', initialdir='/Applications', filetypes=[('Applications', '*.app')])
        elif sys.platform == 'win32':
            options = dict(title='Choose your photo editor', filetypes=[('Applications', '*.exe')])
        else:
            options = dict(title='Choose your photo editor executable')
        if name: options['title'] = 'Choose the installed ' + name + ' application'
        path = filedialog.askopenfilename(**options)
        if not path: return None
        editor = Path(path)
        if sys.platform == 'darwin' and (editor.suffix.lower() != '.app' or not editor.is_dir()):
            messagebox.showerror('Choose an application', 'Choose the editor’s .app application, such as Adobe Photoshop.app.'); return None
        self.editor = editor
        self.editor_label.config(text=editor.name)
        try:
            remember_editor(editor, name)
        except OSError:
            self.status.set('Editor chosen for this session; could not save the preference.')
        return editor

    def open_selected_in_editor(self, name=None):
        if not self.save(): return
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo('No photos selected', 'Select one or more photos first. Use Cmd/Ctrl-click or Shift-click to select several.'); return
        editor = (named_editor(name) or self.choose_editor(name)) if name else (self.editor if self.editor and self.editor.exists() else self.choose_editor())
        if not editor: return
        self.status.set(f'Opening {len(paths)} photos in {editor.name}…')
        generation = self.generation
        def work():
            try:
                count = open_in_editor(paths, editor)
                self.results.put(('editor', generation, f'Sent {count} photos to {editor.name}.'))
            except Exception as exc:
                self.results.put(('editor_error', generation, str(exc)))
        self.pool.submit(work)

    def rename_selected(self):
        if not self.save(): return
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo('Select photos', 'Select one or more photos to rename.'); return
        if any(path in self.errors for path in paths):
            messagebox.showerror('Metadata needs attention', 'Resolve the unreadable sidecar before renaming.'); return
        dialog = tk.Toplevel(self); dialog.title('Rename selected photos'); dialog.geometry('850x600')
        dialog.transient(self); dialog.grab_set()
        form = ttk.Frame(dialog,padding=12); form.pack(fill='x')
        prefix = tk.StringVar(value='Photo'); start = tk.StringVar(value='1'); digits = tk.StringVar(value='4')
        include_date = tk.BooleanVar(value=True)
        date_format = tk.StringVar(value='YYYYMMDD')
        for text,var in [('Name prefix',prefix),('Start number',start),('Sequence digits',digits)]:
            ttk.Label(form,text=text).pack(anchor='w'); ttk.Entry(form,textvariable=var).pack(fill='x',pady=(0,6))
        ttk.Checkbutton(form,text='Include date captured',variable=include_date).pack(anchor='w')
        date_row = ttk.Frame(form); date_row.pack(fill='x',pady=(4,6))
        ttk.Label(date_row,text='Date format').pack(side='left',padx=(0,12))
        ttk.Combobox(date_row,textvariable=date_format,values=('YYYYMMDD','DDMMYY'),state='readonly',width=14).pack(side='left')
        example = tk.StringVar()
        ttk.Label(form,textvariable=example,wraplength=800).pack(anchor='w',pady=10)
        def update_example(*_):
            sample = '20261008' if date_format.get() == 'YYYYMMDD' else '081026'
            middle = '_'+sample if include_date.get() else ''
            example.set(f'Example: Photo{middle}_0001.jpg. Existing files are never overwritten. Sidecars follow renamed photos.')
        date_format.trace_add('write',update_example)
        include_date.trace_add('write',update_example)
        update_example()
        tree = ttk.Treeview(dialog,columns=('old','new','date'),show='headings')
        for key,title in [('old','Current filename'),('new','New filename'),('date','Date captured')]: tree.heading(key,text=title); tree.column(key,width=250)
        tree.pack(fill='both',expand=True,padx=12)
        note = tk.StringVar(value='Preview filenames before renaming.'); ttk.Label(dialog,textvariable=note,wraplength=800,padding=12).pack(fill='x')
        plan = [None]; busy = [False]
        buttons = ttk.Frame(dialog,padding=12); buttons.pack(fill='x')
        def invalidate(*args): plan[0] = None; rename_button.configure(state='disabled')
        for var in [prefix,start,digits,include_date,date_format]: var.trace_add('write',invalidate)
        def preview_names():
            try: plan[0] = rename_plan(paths,prefix.get(),int(start.get()),int(digits.get()),include_date.get(),'%Y%m%d' if date_format.get() == 'YYYYMMDD' else '%d%m%y')
            except Exception as exc:
                note.set(str(exc)); invalidate(); return
            tree.delete(*tree.get_children())
            for old,new,date in plan[0].photos: tree.insert('', 'end',values=(old.name,new.name,date.strftime('%Y-%m-%d %H:%M:%S') if date else 'Unavailable'))
            note.set(f'{len(paths)} photos ready. Rename changes filenames in this folder.'); rename_button.configure(state='normal')
        def run():
            if plan[0] is None or busy[0]: return
            busy[0] = True; rename_button.configure(state='disabled'); preview_button.configure(state='disabled'); cancel_button.configure(state='disabled')
            for child in form.winfo_children():
                try: child.configure(state='disabled')
                except tk.TclError: pass
            note.set('Renaming photos and sidecars…')
            def work():
                try: self.results.put(('renamed',self.generation,(apply_rename(plan[0]),dialog)))
                except Exception as exc: self.results.put(('rename_error',self.generation,(str(exc),dialog)))
            self.pool.submit(work)
        dialog.protocol('WM_DELETE_WINDOW',lambda: None if busy[0] else dialog.destroy())
        preview_button = ttk.Button(buttons,text='Preview names',command=preview_names); preview_button.pack(side='left')
        rename_button = ttk.Button(buttons,text='Rename photos',command=run,state='disabled'); rename_button.pack(side='right')
        cancel_button = ttk.Button(buttons,text='Cancel',command=dialog.destroy); cancel_button.pack(side='right',padx=6)
        preview_names()

    def upload_selected(self):
        if not self.save(): return
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo('Upload photos', 'Select one or more images first.')
            return
        dialog = tk.Toplevel(self)
        dialog.title('Upload selected photos')
        dialog.geometry('600x530')
        dialog.transient(self)
        dialog.grab_set()
        form = ttk.Frame(dialog, padding=14)
        form.pack(fill='both', expand=True)
        values = {
            'protocol': tk.StringVar(value='FTPS'),
            'host': tk.StringVar(),
            'port': tk.StringVar(),
            'username': tk.StringVar(),
            'password': tk.StringVar(),
            'directory': tk.StringVar(),
        }
        ttk.Label(form, text=f'{len(paths)} selected photograph(s)', font=('Helvetica', 12, 'bold')).pack(anchor='w')
        ttk.Label(form, text='FTP transfers are unencrypted; use FTPS or SFTP when your server supports it.', wraplength=550).pack(anchor='w', pady=(6,12))
        for key, title in [('protocol','Destination type'),('host','Server address'),('port','Port (optional)'),('username','Username'),('password','Password'),('directory','Remote folder (optional)')]:
            ttk.Label(form, text=title).pack(anchor='w')
            if key == 'protocol':
                control = ttk.Combobox(form, textvariable=values[key], state='readonly', values=('FTP','FTPS','SFTP'))
            else:
                control = ttk.Entry(form, textvariable=values[key], show='*' if key == 'password' else '')
            control.pack(fill='x', pady=(0,5))
        status = tk.StringVar(value='Ready to upload. Files are transmitted individually.')
        ttk.Label(form, textvariable=status, wraplength=550).pack(anchor='w', pady=(8,4))
        progressbar = ttk.Progressbar(form, mode='determinate', maximum=len(paths))
        progressbar.pack(fill='x', pady=(0,10))
        controls = ttk.Frame(form)
        controls.pack(fill='x')
        upload_button = ttk.Button(controls, text='Start upload')
        upload_button.pack(side='right')
        close_button = ttk.Button(controls, text='Close', command=dialog.destroy)
        close_button.pack(side='right', padx=7)
        transfer_events = queue.Queue()
        running = [False]
        def poll_transfer():
            if not dialog.winfo_exists(): return
            try:
                while True:
                    kind, payload = transfer_events.get_nowait()
                    if kind == 'progress':
                        done, total, name, error = payload
                        progressbar['value'] = done
                        status.set(f'{done} of {total} sent: {name}' if not error else f'Failed: {name} — {error}')
                    elif kind == 'done':
                        status.set(f'Successfully uploaded {payload} photographs.')
                        upload_button.configure(state='normal')
                        close_button.configure(state='normal')
                        running[0] = False
                    elif kind == 'error':
                        status.set(str(payload))
                        upload_button.configure(state='normal')
                        close_button.configure(state='normal')
                        running[0] = False
            except queue.Empty:
                pass
            dialog.after(100, poll_transfer)
        def start_upload():
            if running[0]: return
            try:
                port = int(values['port'].get()) if values['port'].get().strip() else 0
                destination = Destination(values['protocol'].get(), values['host'].get().strip(),
                    values['username'].get().strip(), values['password'].get(), values['directory'].get().strip(), port)
                from delivery import validate
                validate(destination)
            except (ValueError, TypeError) as exc:
                messagebox.showerror('Upload settings', str(exc), parent=dialog)
                return
            running[0] = True
            upload_button.configure(state='disabled')
            close_button.configure(state='disabled')
            status.set('Connecting…')
            def work():
                try:
                    count = upload_files(paths, destination,
                        progress=lambda *event: transfer_events.put(('progress', event)))
                    transfer_events.put(('done', count))
                except Exception as exc:
                    transfer_events.put(('error', str(exc)))
            self.pool.submit(work)
        upload_button.configure(command=start_upload)
        dialog.protocol('WM_DELETE_WINDOW', lambda: None if running[0] else dialog.destroy())
        poll_transfer()

    def csv_export(self):
        if not self.save(): return
        file = filedialog.asksaveasfilename(title='Save caption spreadsheet', defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if not file: return
        try:
            with open(file, 'w', encoding='utf-8-sig', newline='') as out:
                writer = csv.writer(out)
                writer.writerow(['Filename', 'Rating', 'Label', 'Caption', 'Photographer', 'Copyright', 'Keywords'])
                def safe(value):
                    value = str(value)
                    return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) else value
                for path in self.visible:
                    d = self.metadata[path]
                    writer.writerow([safe(path.name), d['rating'], safe(d['label']), safe(d['caption']), safe(d['creator']), safe(d['copyright']), safe('; '.join(d['keywords']))])
            self.status.set(f'Exported captions for {len(self.visible)} visible photos.')
        except Exception as exc: messagebox.showerror('CSV export failed', str(exc))
    def batch_caption(self):
        if self.current is None or not self.save(): return
        paths = self.picks()
        if not paths:
            messagebox.showinfo('No picks', 'Pick photos with P first.'); return
        if not messagebox.askyesno('Apply fields to picks', f'Replace caption, photographer, copyright and keywords on {len(paths)} picks with the current fields? Ratings stay as they are.'):
            return
        template = self.data()
        count = 0
        try:
            for path in paths:
                if path in self.errors: raise ValueError(self.errors[path])
                data = dict(self.metadata[path])
                for key in ['caption', 'creator', 'copyright', 'keywords']: data[key] = template[key]
                save_metadata(path, data)
                self.metadata[path] = data
                count += 1
            self.status.set(f'Updated {count} picks.')
        except Exception as exc: messagebox.showerror('Batch stopped', f'Updated {count} photos before stopping: {exc}')
    def help(self):
        messagebox.showinfo('Contact Sheet shortcuts', 'Cmd/Ctrl-click: add or remove a photo\nShift-click: select a range across pages\nCmd/Ctrl+A: select all filtered photos\nEscape: clear selection\nOpen in…: Photoshop, Photo Craft, or another editor\nRename selected: sequence and capture date\n← / →: previous / next\n0–5: star rating\nP: green pick\nX: reject\nU: clear rating and pick\nZ: fit / 100% preview, drag to pan\n⌘/Ctrl+S: save caption\n⌘/Ctrl+O: open folder\n\nEdits save before changing photos or closing.\nShortcuts pause while typing in fields.\nOpen folders are not scanned recursively.')
    def close(self):
        if not self.save(): return
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.preview_pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()

if __name__ == '__main__':
    import sys
    app = ContactSheet()
    if '--smoke-test' in sys.argv:
        app.after(1000, app.close)
    app.mainloop()
