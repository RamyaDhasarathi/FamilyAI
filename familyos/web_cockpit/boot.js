/* Dark is the cockpit's default, a calm room at any hour; only a stored
   "light" changes it. Wrapped because localStorage throws in a private window. */
try {
  if (localStorage.getItem('familyos.theme') !== 'light') document.documentElement.setAttribute('data-theme', 'dark');
} catch (e) { document.documentElement.setAttribute('data-theme', 'dark'); }
