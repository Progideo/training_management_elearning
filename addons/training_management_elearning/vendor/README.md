# Bundled players

Unmodified release artifacts already qualified locally:
- h5p-standalone 3.8.2, MIT (LICENSE alongside).
- scorm-again 3.5.0, MIT (LICENSE alongside).

Only these distributions are bundled; no prototype addon code is deployed.

`h5p/frame.bundle.js` embeds H5P core JavaScript (`H5P.jQuery`, `H5P.Tooltip`) under the MIT terms retained by
the operator on 2 November 2026. [H5P licensing](https://h5p.org/licensing) says H5P uses MIT wherever possible and that the
GPL requirement comes from third-party purification code in the PHP library, which is not bundled here. The
[JavaScript API documentation](https://h5p.org/documentation/api/index.html) carries an MIT notice from Joubel AS.
Upstream `h5p/h5p-php-library` still ships a GPL-3.0 `LICENSE.txt` and no source states the license of its `js/` files by name.

Content libraries inside uploaded H5P packages retain their own licenses,
which the author must declare at import. Supported initial content: TrueFalse 1.8,
SCORM 1.2 single SCO. No SCORM 2004, multi-SCO or general H5P claim.
Files are served only through the scoped content origin, never as private content
under the portal's static directory. Package bytes remain in private database fields.
