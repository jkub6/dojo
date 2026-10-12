# Browser decoder

`fzstd.js` is the UMD distribution of [fzstd 0.1.1](https://github.com/101arrowz/fzstd), retrieved
from the versioned npm tarball `https://registry.npmjs.org/fzstd/-/fzstd-0.1.1.tgz`. It differs from
`package/umd/index.js` only by an appended semicolon and newline. The vendored file's SHA-256 is
`fbd81d18a71617da37d231f258d8e6303f6bfa522c0d67d9ec6ce06bfbc5614a`.

The adjacent `fzstd.LICENSE` carries the upstream MIT notice, which is also embedded in every
generated decoder. To update it, review the upstream release, replace the UMD file and license,
update the checksum here, and run the Python and Chromium round-trip tests. Never fetch decoder code
while opening a publication.

The supported compression window is at most 32 MiB (`window_log=25`), matching
[the upstream decoder limit](https://github.com/101arrowz/fzstd#considerations). This bounds history
size, not the total size of a streamed document.
