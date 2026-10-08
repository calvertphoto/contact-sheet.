"""Contact Sheet: a local, open-source culling and captioning desktop app."""
from __future__ import annotations
import csv
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from PIL import ImageTk
from core import photos, preview, load_metadata, save_metadata, export_photos, empty_metadata

class ContactSheet(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Contact Sheet — Cull • Caption • Export')
        self.geometry('1380x860')
        self.minsize(1000, 680)
        self.configure(bg='#171b22')
        self.paths = []
        self.visible = []
        self.metadata = {}
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
        self._build()
        self._bind()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(70, self._poll)

    def _build(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#212733', foreground='#f2f4f8', fieldbackground='#141922')
        style.configure('TButton', padding=(10, 7))
        style.configure('TEntry', fieldbackground='#141922')
        style.configure('TCombobox', fieldbackground='#141922')
        bar = ttk.Frame(self, padding=12)
        bar.pack(fill='x')
        ttk.Label(bar, text='CONTACT SHEET', font=('Helvetica', 17, 'bold')).pack(side='left', padx=(0, 18))
        ttk.Button(bar, text='Open folder', command=self.open_folder).pack(side='left')
        ttk.Button(bar, text='Export picks', command=self.export).pack(side='left', padx=6)
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
        self.canvas = tk.Canvas(center, background='#0d1117', highlightthickness=0)
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
        ttk.Label(right, text='Caption', padding=(0, 14, 0, 4)).pack(anchor='w')
        self.caption = tk.Text(right, height=9, width=29, wrap='word', bg='#141922', fg='#f2f4f8', insertbackground='white', undo=True, relief='flat', padx=8, pady=8)
        self.caption.pack(fill='x')
        self.caption.bind('<<Modified>>', self.modified)
        self.fields = {}
        for name, title in [('creator', 'Photographer / byline'), ('copyright', 'Copyright'), ('keywords', 'Keywords (comma-separated)')]:
            ttk.Label(right, text=title, padding=(0, 12, 0, 4)).pack(anchor='w')
            variable = tk.StringVar()
            ttk.Entry(right, textvariable=variable).pack(fill='x')
            variable.trace_add('write', lambda *a: self.mark_dirty())
            self.fields[name] = variable
        ttk.Button(right, text='Save caption  ⌘/Ctrl+S', command=self.save).pack(fill='x', pady=(18, 8))
        ttk.Button(right, text='Apply these fields to picks…', command=self.batch_caption).pack(fill='x')
        ttk.Label(right, text='Metadata saves to XMP sidecars.\nOriginal photos are never rewritten.\n\nPick = green label; reject = −1 rating.\nExport copies picks to a new folder.', wraplength=260, padding=(0, 16, 0, 0)).pack(anchor='w')
        ttk.Label(self, textvariable=self.status, padding=8).pack(fill='x')

    def _bind(self):
        for key, action in [('<Left>', lambda: self.move(-1)), ('<Right>', lambda: self.move(1)), ('<p>', lambda: self.rate(label='Green')), ('<x>', lambda: self.rate(-1, '')), ('<u>', lambda: self.rate(0, '')), ('<z>', self.toggle_zoom)]:
            self.bind(key, lambda e, fn=action: self.shortcut(e, fn))
        for n in range(6):
            self.bind(str(n), lambda e, rating=n: self.shortcut(e, lambda: self.rate(rating)))
        for modifier in ('Control', 'Command'):
            try:
                self.bind(f'<{modifier}-s>', lambda e: self.save())
                self.bind(f'<{modifier}-o>', lambda e: self.open_folder())
            except tk.TclError:
                pass
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
            box = tk.Frame(self.grid, bg='#263547' if path == self.current else '#171b22', padx=4, pady=4)
            box.grid(row=row, column=col, sticky='nsew', padx=2, pady=2)
            button = tk.Label(box, text='Loading…', bg='#171b22', fg='white', width=14, height=4)
            button.pack(fill='both', expand=True)
            button.bind('<Button-1>', lambda e, p=path: self.select(p))
            data = self.metadata[path]
            symbol = 'REJECT' if data['rating'] == -1 else '★'*data['rating']
            if data['label'] == 'Green': symbol = 'PICK ' + symbol
            label = tk.Label(box, text=path.name[:18]+'\n'+symbol, bg=box['bg'], fg='#7cdea5' if data['label']=='Green' else '#eef2f6', font=('Helvetica', 9))
            label.pack()
            label.bind('<Button-1>', lambda e, p=path: self.select(p))
            self.thumb_widgets[path] = button
            key = (path, (140, 85), False)
            if key in self.cache: self.set_thumb(path, self.cache[key])
            else: self.request_preview(path, (140, 85), 'thumb')
        for col in range(3): self.grid.columnconfigure(col, weight=1)
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
    def select(self, path):
        if not self.save(): return
        self.current = path
        data = self.metadata[path]
        self.caption.delete('1.0', 'end')
        self.caption.insert('1.0', data['caption'])
        self.caption.edit_modified(False)
        for name, var in self.fields.items(): var.set(', '.join(data[name]) if name=='keywords' else data[name])
        self.dirty = False
        self.filename.config(text=path.name)
        if path in self.visible: self.page = self.visible.index(path)//self.page_size
        self.render_grid()
        self.show_preview()
        self.focus_set()
        if path in self.errors: self.status.set(self.errors[path])
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
        self.canvas.create_text(20, 20, anchor='nw', fill='white', text='Loading preview…')
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
                if generation != self.generation and kind not in ('export', 'export_error'):
                    if kind == 'thumb': self.pending.discard(payload[0])
                    continue
                if kind == 'folder':
                    if not self.save(): continue
                    self.folder, self.paths, self.metadata, self.errors = payload
                    self.current = None
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
                elif kind == 'error': messagebox.showerror('Operation failed', payload)
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
                        self.canvas.create_text(20, 20, anchor='nw', fill='white', width=440, text=value)
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
        paths = self.picks()
        if any(p in self.errors for p in paths):
            messagebox.showerror('Metadata needs attention', 'One or more picks has unreadable metadata. Resolve the sidecar error before exporting.'); return
        if not paths:
            messagebox.showinfo('No picks yet', 'Press P to pick photos, then export them.'); return
        folder = filedialog.askdirectory(title=f'Copy {len(paths)} picks to an empty destination folder')
        if not folder: return
        self.status.set('Copying picks…')
        # Export off the UI thread; present a result without silently retrying.
        generation = self.generation
        def work():
            try:
                count = export_photos(paths, folder)
                self.results.put(('export', generation, f'Copied {count} photos and available sidecars.'))
            except Exception as exc:
                self.results.put(('export_error', generation, 'Some files may have been copied before stopping. ' + str(exc)))
        # Use a dedicated completion callback via a second queue event handler.
        self.pool.submit(work)
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
        messagebox.showinfo('Contact Sheet shortcuts', '← / →: previous / next\n0–5: star rating\nP: green pick\nX: reject\nU: clear rating and pick\nZ: fit / 100% preview, drag to pan\n⌘/Ctrl+S: save caption\n⌘/Ctrl+O: open folder\n\nEdits save before changing photos or closing.\nShortcuts pause while typing in fields.\nOpen folders are not scanned recursively.')
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
