"""Capture-date-aware rename plans, with collision checks and sidecar preservation."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import xml.etree.ElementTree as ET
from core import sidecar, FORMATS


def capture_date(path):
    """Read camera capture time; never substitute filesystem modification time."""
    try:
        import exifread
        with Path(path).open('rb') as file:
            tags = exifread.process_file(file, details=False, stop_tag='DateTimeOriginal')
        value = str(tags.get('EXIF DateTimeOriginal', ''))
        if value:
            return datetime.strptime(value[:19], '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    try:
        from PIL import Image
        with Image.open(path) as image:
            exif = image.getexif()
            value = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x9003)
        if value: return datetime.strptime(str(value)[:19], '%Y:%m:%d %H:%M:%S')
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    try:
        file = sidecar(path)
        if file.exists():
            root = ET.parse(file).getroot()
            for uri,name in [('http://ns.adobe.com/exif/1.0/','DateTimeOriginal'),('http://ns.adobe.com/photoshop/1.0/','DateCreated')]:
                key = '{'+uri+'}'+name
                for node in root.iter():
                    value = node.get(key) or (node.text if node.tag == key else None)
                    if value: return datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ET.ParseError, OSError, ValueError):
        pass
    return None

@dataclass(frozen=True)
class RenamePlan:
    photos: tuple
    copies: tuple
    remove: tuple
    signatures: tuple


def rename_plan(paths, prefix='Photo', start=1, digits=4, include_date=True, date_format='%Y%m%d'):
    paths = [Path(p) for p in paths]
    if not paths: raise ValueError('Select photos to rename first.')
    if len(set(paths)) != len(paths): raise ValueError('Duplicate photos in selection.')
    if start < 0 or digits not in range(1,10): raise ValueError('Use a nonnegative sequence start and 1–9 digits.')
    prefix = prefix.strip()
    if not prefix or re.search(r'[<>:"/\\|?*\x00-\x1f]',prefix) or prefix.endswith(('.', ' ')):
        raise ValueError('Enter a filename prefix without slashes or special filename characters.')
    if prefix.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('This prefix is reserved by Windows. Choose another name.')
    photos, copies, remove = [], [], set()
    for sequence, path in enumerate(paths,start):
        if not path.is_file(): raise FileNotFoundError(str(path))
        date = capture_date(path)
        if include_date and date is None: raise ValueError(f'{path.name}: capture date is unavailable. Turn off Include capture date to rename without a date.')
        parts = [prefix]
        if include_date: parts.append(date.strftime(date_format))
        parts.append(str(sequence).zfill(digits))
        target = path.with_name('_'.join(parts)+path.suffix)
        photos.append((path,target,date))
        if target == path: continue
        copies.append((path,target)); remove.add(path)
        meta = sidecar(path)
        if meta.exists():
            copies.append((meta,target.with_name(target.name+'.xmp')))
            # Shared conventional sidecars stay with unselected RAW/JPEG siblings.
            siblings = [p for p in path.parent.iterdir() if p.suffix.lower() in FORMATS and p.stem == path.stem]
            if meta.name == path.name+'.xmp' or all(p in paths for p in siblings): remove.add(meta)
    targets = [target for _,target in copies]
    if len({str(p).casefold() for p in targets}) != len(targets): raise FileExistsError('Rename would create duplicate filenames.')
    for target in targets:
        if any(p.name.casefold() == target.name.casefold() for p in target.parent.iterdir()):
            raise FileExistsError(f'{target.name} already exists. Change the prefix or starting number.')
    mapping = {source:target for source,target,_ in photos}
    for source in list(remove):
        if source.suffix.lower() == '.xmp' and source.name == source.stem + '.xmp':
            # Only conventional sidecars share the photo stem.
            siblings = [p for p in source.parent.iterdir() if p.suffix.lower() in FORMATS and p.stem == source.stem]
            if any(mapping.get(p,p) == p for p in siblings): remove.discard(source)
    sources = {source for source,_ in copies}
    signatures = tuple((p,p.stat().st_size,p.stat().st_mtime_ns) for p in sources)
    return RenamePlan(tuple(photos),tuple(copies),tuple(remove),signatures)


def _copy_exclusive(source,target):
    try:
        os.link(source,target)
    except FileExistsError: raise
    except OSError:
        with source.open('rb') as src, target.open('xb') as dst:
            try: shutil.copyfileobj(src,dst)
            except Exception:
                target.unlink(missing_ok=True)
                raise
        try: shutil.copystat(source,target)
        except Exception:
            target.unlink(missing_ok=True)
            raise


def apply_rename(plan):
    for path,size,mtime in plan.signatures:
        if not path.exists() or (path.stat().st_size,path.stat().st_mtime_ns) != (size,mtime):
            raise ValueError('A source file changed after preview. Preview the names again.')
    made = []
    try:
        for source,target in plan.copies:
            _copy_exclusive(source,target); made.append((source,target))
        for source in plan.remove: source.unlink()
    except Exception as exc:
        # Restore any removed originals before removing new names.
        recovery_errors = []
        for source,target in made:
            try:
                if not source.exists(): _copy_exclusive(target,source)
            except Exception as error: recovery_errors.append(str(error))
        if recovery_errors:
            raise RuntimeError('Rename stopped. Keep both sets of files for recovery: '+ '; '.join(recovery_errors)) from exc
        for _,target in made: target.unlink(missing_ok=True)
        raise
    return {source:target for source,target,_ in plan.photos}
