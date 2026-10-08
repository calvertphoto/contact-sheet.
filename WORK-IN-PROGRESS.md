# Contact Sheet 0.2.0 checkpoint

Implemented: multiple selection and export; handoff to a chosen editor; gray interface; generated contact-sheet icon; eight IPTC sections with repeated-entry forms; XMP sidecar round trips; four-platform build workflow.

Local metadata tests pass. Graphical smoke tests require a desktop host and run on all GitHub build runners. Build and release publication status must be checked in GitHub Actions before handing out downloads.

Mac rawpy pins: 0.25.1 Intel, 0.27.1 Apple Silicon. Windows builds are copied to runner.temp because the repository name has a trailing period. Linux uses xvfb for desktop checks.
