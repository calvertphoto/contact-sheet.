# Contact Sheet

An open-source desktop photo culling and captioning app, built around the first pass through a news or sports assignment. Version **0.3.0 — prototype**. MIT licensed; no accounts, cloud uploads, subscription, analytics, or AI features.

This is an independent project, not affiliated with Photo Mechanic or Camera Bits. It is a starting point for a simpler workflow, not a feature-complete replacement.

## Download the standalone app

Open **[Releases](https://github.com/calvertphoto/contact-sheet./releases)** and select the ZIP for your Mac:

- **macOS-Apple-Silicon** for M1, M2, M3, M4 and later Apple chips.
- **macOS-Intel** for Intel Macs.

Unzip it and open **ContactSheet.app**. You do not need Python for these packaged builds. To check your chip, use Apple menu → About This Mac. Packages require macOS 15 or newer because they are built on macOS 15. Builds are unsigned and not notarized; macOS may require permission through System Settings → Privacy & Security.

The first release appears only after all build jobs succeed. Below are source setup instructions for development.

## Run the source on a Mac

1. Unzip this download into a writable folder, such as Documents.
2. Install **Python 3.12 or later using the macOS installer from https://www.python.org/downloads/macos/**. That installer includes the Tk interface library. If you already have it, skip this step.
3. Double-click **Launch-Mac.command**. The first launch downloads Pillow into a project-local virtual environment, so it needs an internet connection. Subsequent launches work offline.
4. Click **Open folder**, choose a photo folder, and click a thumbnail.

If Finder won't launch the script, use Terminal inside the extracted folder:

```sh
bash Launch-Mac.command
```

The source download is not a prebuilt `.app`. The GitHub workflow included in this project is intended to produce standalone apps after the project has been uploaded to a repository. It has not been run in this development environment.

### Enable RAW previews

After the first launch, quit the app and run these commands from its folder:

```sh
.venv/bin/python -m pip install -r requirements-raw.txt
bash Launch-Mac.command
```

RAW files use LibRaw through rawpy. Embedded previews are preferred; half-size processing is used when a file has no embedded thumbnail. Actual compatibility depends on the camera and LibRaw version. No real camera RAW fixtures have been verified in this initial build. At 100%, RAW displays the embedded preview resolution, which may be smaller than the sensor image.

## Windows and Linux

Windows: install Python from https://www.python.org/downloads/ and double-click `Launch-Windows.bat`.

Linux: install Python with your distribution's Tk package, then run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

## Assignment workflow

- **Browse:** folder-based, paginated thumbnails with a large preview. JPEG, TIFF, PNG, WebP and BMP are supported by Pillow; common RAW extensions are shown with optional rawpy preview support.
- **Cull:** use arrow keys to move, 0–5 for stars, P for a green pick, X to reject, U to clear rating and label. Existing labels other than Green are preserved until changed.
- **Inspect:** Z switches fit / 100%; drag the image to pan. RAW uses its embedded preview where available. JPEG orientation is honored.
- **Caption:** enter caption, photographer, copyright and comma-separated keywords. Use Cmd/Ctrl+S. Edits also save before moving to another photo or closing. Typing in a field disables culling keys.
- **Batch:** “Apply these fields to picks” replaces the four caption fields on all picks after a confirmation. It preserves ratings and labels. Individual writes are atomic, but the batch as a whole is not transactional; an error can leave some picks updated.
- **Filter:** show picks, rejects or a minimum star rating; search filename, caption and keywords. Filters never delete files. When a rating changes, a photo may leave the current filter; it stays in the preview until you navigate.
- **Deliver:** “Export picks” copies all green, non-rejected picks from the open folder, with available sidecars, into a destination. Existing matching filenames stop the export. Images are copied byte-for-byte, not re-encoded.
- **Spreadsheet:** “Caption CSV” exports the currently visible filtered set with UTF-8 captions and keywords. Text that could be interpreted as a spreadsheet formula is prefixed with an apostrophe.

Opening a folder scans only its immediate contents. It does not recurse. Folder/card import here means browsing; it is not an ingest/backup tool.

## How metadata works

Original photos are read only. Changes go into **`filename.ext.xmp`**, e.g. `DSC_1234.NEF.xmp`. This avoids collisions between a RAW file and JPEG with the same stem. The app also reads conventional `filename.xmp` sidecars and carries their unedited XML fields forward into the per-image sidecar. A malformed sidecar blocks metadata edits and remains untouched.

Fields use standard XMP properties: `xmp:Rating`, `xmp:Label`, `dc:description`, `dc:creator`, `dc:rights`, `dc:subject`. Updating the four caption fields replaces their existing values, including alternative translations or multiple creators, with the text entered in the app. Other properties are preserved. Existing legacy IPTC caption/byline/copyright/keywords can be read from supported JPEG/TIFF files when no sidecar is present. Embedded XMP in image files is not imported in this version.

**Interoperability limit:** many photo tools expect `filename.xmp` for RAW and embedded metadata for JPEG. They may not automatically read the full-name sidecars produced here. This version does not embed IPTC/XMP into deliverable JPEGs. Keep the CSV and sidecars with your photos, and confirm your receiving editor's workflow before relying on them for an assignment.

There is no caption history or undo for saved ratings. Copying picks is non-destructive; interrupted exports may leave a partial destination. Files on read-only cards can be browsed, but metadata cannot be saved beside them: copy them into a writable folder first.

## Publish on GitHub and build apps

1. Create an empty repository called `contact-sheet` in your GitHub account. Choose public or private according to your preference.
2. Upload the contents of this folder to its root, including `.github/workflows/build.yml`. Alternatively, in this project folder:

```sh
git init -b main
git add .
git commit -m "Initial Contact Sheet desktop app"
git remote add origin https://github.com/calvertphoto/contact-sheet..git
git push -u origin main
```

3. Open **Actions → Test and build desktop apps**. A push to `main` starts the workflow, or use **Run workflow**.
4. After a successful run, download the matching artifact: **macOS-Apple-Silicon**, **macOS-Intel**, . Mac artifacts contain an additional app ZIP; unpack that ZIP to get `ContactSheet.app`. Windows source can be run with the included launcher; standalone Windows builds are not included in this initial Mac release.

GitHub Actions builds on each operating system using PyInstaller. The workflow installs rawpy for RAW support, runs core tests, checks basic Tk interactions, and uploads builds as Actions artifacts. After all builds pass, it publishes a prerelease with ZIP downloads. Re-running this version replaces its release assets. Builds are unsigned and not notarized. The workflow checks that the packaged Mac application launches, but the apps still need real assignment testing on Macs/Windows machines; a successful source test run is not evidence of a packaged app working.

## Development and verification

From this folder:

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m compileall -q app.py core.py
```

Core tests cover metadata round-trips, original-image preservation, unknown-property preservation, RAW/JPEG sidecar separation, malformed XML handling, invalid ratings, reject/clear persistence, export copies and collision refusal, EXIF orientation, and preview sizing. A display-dependent UI smoke test skips on headless Linux and runs in the desktop build workflow.

Known first-version gaps: no dual-destination ingest, file renaming, code replacements, FTP delivery, embedded metadata writing, GPS/date editor, side-by-side comparison, HEIC, video, recursive catalog, color-managed preview guarantee, or full-resolution RAW rendering. Large folder metadata scans run in the background; batch caption updates currently run on the UI thread. Thumbnail caching is bounded but not persisted between sessions.

## Version 0.2

Command/Control-click selects several photos; Shift-click selects a range. Use Export selected to copy photos and their XMP sidecars, or Open in app to send originals to Photoshop or another installed editor.

Edit IPTC fields opens eight scrollable sections. Repeated entries such as locations, artwork, image creators, registry entries and licensors have an Edit rows form. List fields use semicolons. Enumerated rights and media properties accept standard PLUS or IPTC URI values. Metadata is stored in XMP sidecars; originals are never rewritten.

Download Apple Silicon, Intel Mac, Windows or Linux builds from the v0.2.0 release once the build workflow finishes. Mac: extract the ZIP and open ContactSheet.app. Windows: extract the entire ZIP and open ContactSheet.exe inside its folder. Linux: extract the tar.gz and run ContactSheet/ContactSheet.

## Version 0.3

Rename selected previews a new filename for each selected photo, using a name prefix, optional capture date, starting sequence number and digit count. For example, Aces_20261008_0001.jpg. Capture dates come from camera EXIF or XMP metadata; modification dates are never substituted. Missing capture dates stop the date-based rename until you turn off the date option. Renaming keeps image bytes and moves associated sidecars with the new names. Collision checks refuse existing filenames.

The Export selected button has been removed. Open in… offers Photoshop, Photo Craft and Other editor. Choose the installed application the first time; named editor choices are remembered independently.

[Download version 0.3.0](https://github.com/calvertphoto/contact-sheet./releases/tag/v0.3.0).

## Upload selected photos (version 0.4.1)

Select photos and choose **Upload selected…**. The supported destinations are **FTP**, **FTPS** and **SFTP**. Enter your server address, username, password, optional port and remote folder. Transfers are sequential, with progress and two retry attempts. Passwords are not persisted. FTPS encrypts authentication and transfer traffic; SFTP uses SSH with existing trusted host keys. Standard FTP is unencrypted. Remote servers may overwrite files with matching names. The app sends selected original images as-is, not XMP sidecars. Use copies for initial tests.

[Download the latest release](https://github.com/calvertphoto/contact-sheet./releases/latest).
