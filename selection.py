"""Selection behavior shared by thumbnail clicks and keyboard shortcuts."""
class PhotoSelection:
    def __init__(self):
        self.selected = set()
        self.anchor = None

    def click(self, path, visible, toggle=False, extend=False):
        if path not in visible:
            return
        if extend and self.anchor in visible:
            a, b = sorted((visible.index(self.anchor), visible.index(path)))
            span = set(visible[a:b+1])
            self.selected = self.selected | span if toggle else span
        elif toggle:
            if path in self.selected:
                self.selected.remove(path)
            else:
                self.selected.add(path)
            self.anchor = path
        else:
            self.selected = {path}
            self.anchor = path

    def select_all(self, visible):
        self.selected = set(visible)
        if self.anchor not in self.selected:
            self.anchor = visible[0] if visible else None

    def clear(self):
        self.selected.clear()
        self.anchor = None

    def retain_visible(self, visible):
        self.selected.intersection_update(visible)
        if self.anchor not in visible:
            self.anchor = None

    def ordered(self, visible):
        return [path for path in visible if path in self.selected]
