"""Open original files in a selected desktop editor without shell interpolation."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

def config_path():
    if sys.platform == 'darwin':
        return Path.home()/'Library'/'Application Support'/'ContactSheet'/'settings.json'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home()))/'ContactSheet'/'settings.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'contact-sheet'/'settings.json'

def saved_editor(name=None):
    try:
        settings = json.loads(config_path().read_text())
        value = settings.get('editors', {}).get(name, '') if name else settings.get('editor', '')
        path = Path(value)
        return path if value and path.exists() else None
    except (OSError, ValueError, TypeError):
        return None

def remember_editor(path, name=None):
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w') as out:
            try: settings = json.loads(target.read_text())
            except (OSError, ValueError): settings = {}
            if name: settings.setdefault('editors', {})[name] = str(Path(path).resolve())
            else: settings['editor'] = str(Path(path).resolve())
            json.dump(settings, out)
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)

def open_in_editor(paths, editor):
    """Pass complete paths as distinct arguments; report OS launch failures."""
    paths = [Path(p).resolve() for p in paths]
    editor = Path(editor).resolve()
    if not paths:
        raise ValueError('Select one or more photos first.')
    if not editor.exists():
        raise FileNotFoundError('The selected editor is no longer installed. Choose another app.')
    if any(not p.is_file() for p in paths):
        raise FileNotFoundError('One or more selected photos is no longer available.')
    if sys.platform == 'darwin':
        if editor.suffix.lower() != '.app' or not editor.is_dir():
            raise ValueError('Choose an application ending in .app, such as Adobe Photoshop.app.')
        prefix = ['/usr/bin/open', '-a', str(editor)]
        max_bytes = 48000
    elif sys.platform == 'win32':
        if editor.suffix.lower() != '.exe' or not editor.is_file():
            raise ValueError('Choose the editor’s .exe application file.')
        prefix = [str(editor)]
        max_bytes = 14000  # leave room for UTF-16 Windows command line quoting
    else:
        if not editor.is_file() or not os.access(editor, os.X_OK):
            raise ValueError('Choose an executable application.')
        prefix = [str(editor)]
        max_bytes = 48000
    batches, batch, used = [], [], sum(len(a.encode('utf-8'))+1 for a in prefix)
    for path in paths:
        argument = str(path)
        cost = len(argument.encode('utf-8'))+3
        if batch and (used + cost > max_bytes or len(batch) >= 50):
            batches.append(batch)
            batch = []
            used = sum(len(a.encode('utf-8'))+1 for a in prefix)
        batch.append(argument)
        used += cost
    if batch:
        batches.append(batch)
    for batch in batches:
        if sys.platform == 'darwin':
            result = subprocess.run(prefix + batch, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    text=True, timeout=30, check=False)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or 'macOS could not open the selected app.')
        else:
            # Editors commonly stay open for hours; launching must not wait for exit.
            subprocess.Popen(prefix + batch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return len(paths)


def named_editor(name):
    saved = saved_editor(name)
    if saved: return saved
    if sys.platform == 'darwin':
        patterns = ['Adobe Photoshop*.app','Adobe Photoshop*/Adobe Photoshop*.app'] if name == 'Photoshop' else ['Photo Craft.app','PhotoCraft.app','Photo Craft*/Photo Craft*.app']
        for folder in [Path('/Applications'),Path.home()/'Applications']:
            for pattern in patterns:
                matches = sorted(folder.glob(pattern),reverse=True)
                if matches: return matches[0]
    return None
