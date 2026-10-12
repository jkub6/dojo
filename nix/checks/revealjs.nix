# Pandoc 3.7's default template uses Reveal.js 5's plugin layout.
# Pin this test fixture so the browser never needs a public CDN.
{fetchzip}:
fetchzip {
  url = "https://registry.npmjs.org/reveal.js/-/reveal.js-5.2.1.tgz";
  hash = "sha256-zvqQZqO7wyitV5fTVnzwgQbtZaXUgY2UypMmVTdb96M=";
}
