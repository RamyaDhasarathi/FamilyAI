/* Light is the default now -- a warm canvas, not a dark console -- so only a
   stored "dark" does anything before the stylesheet paints. Wrapped because
   localStorage throws in a private window, and a theme is not worth failing
   a page load over. */
try {
  if (localStorage.getItem('familyos.theme') === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
} catch (e) { /* default stands */ }
