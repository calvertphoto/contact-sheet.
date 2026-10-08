# Contact Sheet 0.2.0 work checkpoint

Requested changes:
- Multiple photo selection: Command/Control-click, Shift-click, Select All.
- Export selected photos; open them in Photoshop or another chosen editor.
- A photographic contact-sheet application icon.
- Gray interface background instead of black.
- All IPTC categories visible in supplied screenshots: Description, Creator, Event/Location, Workflow, Releases/Artwork, Contact, Licensing, Media.
- Downloadable Apple Silicon, Intel, Windows, and Linux applications.

Current checkpoint: selection model, editor integration, gray theme, and new icon PNG/ICO have been implemented locally. Expanded IPTC UI and metadata storage, cross-platform packaging, tests, and release publication are still in progress. Existing published v0.1.0 remains available.

Continue with these changes before publishing v0.2.0. New Mac builds should retain pinned rawpy 0.25.1 for Intel and 0.27.1 for Apple Silicon. On Windows the repository has a trailing period, so use runner.temp for checkout/build to avoid invalid workspace paths. Linux desktop tests can run with xvfb-run.
