/* Before the stylesheet paints, or a light-theme viewer sees a dark flash on
   every load. Dark is the default, so only a stored "light" does anything.
   Wrapped because localStorage throws in a private window, and a theme is not
   worth failing a page load over. */
try {
  if (localStorage.getItem('familyos.theme') === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  }
} catch (e) { /* default stands */ }
