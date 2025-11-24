# Changelog

## 2.5.4 - 2025-11-22
- Introduce scope-aware staging so tag edits persist across patient/study/series navigation with clear baseline vs pending highlights.
- Add Pending Changes dialog with per-entry commit/discard controls, better sizing, wrapping, and toolbar/menu access.
- Batch commit/discard flows now run unattended and surface a single roll-up summary, plus exit/move safeguards when staging is non-empty.
- Show staged edit counts in the summary bar and gate moves/quit until edits are committed or discarded.

## 2.5.3 - 2025-11-21
- Allow multi-select when adding files through the append workflow.
- Tree selection restores the exact study/series/instance after saving edits.
- Move workflow supports multi-selection and keeps metadata consistent when moving between patients/studies/series.
- Moving (and zip exporting) rewritten files now uses `write_like_original=False`, ensuring valid DICOM headers in exported zips.
- Prevent duplicate patients/studies from appearing after multi-file loads by deduping cached paths.
- Introduce DICOM receive service with inbound placeholders and separate receive logging.
- Add audit log tracking for tag edits with exportable summary dialog.
