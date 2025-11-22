# Changelog

## 2.5.3 - 2025-11-21
- Allow multi-select when adding files through the append workflow.
- Tree selection restores the exact study/series/instance after saving edits.
- Move workflow supports multi-selection and keeps metadata consistent when moving between patients/studies/series.
- Moving (and zip exporting) rewritten files now uses `write_like_original=False`, ensuring valid DICOM headers in exported zips.
- Prevent duplicate patients/studies from appearing after multi-file loads by deduping cached paths.
- Introduce DICOM receive service with inbound placeholders and separate receive logging.
- Add audit log tracking for tag edits with exportable summary dialog.
