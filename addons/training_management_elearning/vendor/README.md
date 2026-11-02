# Bundled players

Unmodified release artifacts already qualified locally:
- h5p-standalone 3.8.2, MIT (LICENSE alongside).
- scorm-again 3.5.0, MIT (LICENSE alongside).

Only these distributions are bundled; no prototype addon code is deployed.

Open point: `h5p/frame.bundle.js` embeds H5P core JavaScript (`H5P.jQuery`, `H5P.Tooltip`).
The h5p-standalone MIT notice does not name it, and upstream `h5p/h5p-php-library` declares
GPL-3.0. The license of that bundled code must be confirmed before external distribution.

Content libraries inside uploaded H5P packages retain their own licenses,
which the author must declare at import. Supported initial content: TrueFalse 1.8,
SCORM 1.2 single SCO. No SCORM 2004, multi-SCO or general H5P claim.
Files are served only through the scoped content origin, never as private content
under the portal's static directory. Package bytes remain in private database fields.
