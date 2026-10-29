/* Orbit: line icons, drawn here so nothing is fetched. currentColor throughout. */
const P = {
  finance: '<circle cx="12" cy="12" r="8.5"/><path d="M9 8h6M9 11h6M9 8c3.5 0 3.5 6 0 6l5 3"/>',
  education: '<path d="M2.5 9.5 12 5l9.5 4.5L12 14z"/><path d="M6.5 11.5V16c3 2.2 8 2.2 11 0v-4.5M21.5 9.5v5"/>',
  household: '<path d="M3.5 11 12 4l8.5 7"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5.5h4V20"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M7.5 13.5h2M11 13.5h2M14.5 13.5h2M7.5 16.8h2M11 16.8h2"/>',
  grocery: '<path d="M3.5 9.5h17l-1.8 9.2a1.6 1.6 0 0 1-1.6 1.3H6.9a1.6 1.6 0 0 1-1.6-1.3z"/><path d="m8 9.5 3-5M16 9.5l-3-5M9 13v3.5M12 13v3.5M15 13v3.5"/>',
  health: '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.3 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10z"/><path d="M7 12.5h3l1.2-2.5 1.8 4.5 1.2-2h2.8"/>',
  memories: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m4 17 5-4.5 3.5 3 3-2.5 4.5 4"/>',
  waiting: '<path d="M7 3.5h10M7 20.5h10M8 3.5c0 5 8 5 8 8.5s-8 3.5-8 8.5M16 3.5c0 5-8 5-8 8.5s8 3.5 8 8.5"/>',
  conflicts: '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.2v.3"/>',
  todos: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8 12.5 3 3 5-6"/>',
  documents: '<path d="M6 3.5h8l4 4V20.5H6z"/><path d="M14 3.5V8h4M9 12h6M9 15.5h6"/>',
  mic: '<rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  send: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  bento: '<rect x="4" y="4" width="7" height="9" rx="1.5"/><rect x="13" y="4" width="7" height="5" rx="1.5"/><rect x="13" y="11" width="7" height="9" rx="1.5"/><rect x="4" y="15" width="7" height="5" rx="1.5"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  up: '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>',
  down: '<path d="M12 5v13M6.5 12.5 12 18l5.5-5.5"/>',
  phone: '<path d="M5 4h4l1.5 4.5-2.3 1.4a11 11 0 0 0 5.9 5.9l1.4-2.3L20 15v4a1.5 1.5 0 0 1-1.6 1.5A16 16 0 0 1 3.5 5.6 1.5 1.5 0 0 1 5 4z"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
  speaker: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6 10h.01M9 10h.01M12 10h.01M15 10h.01M18 10h.01M6 13.5h.01M18 13.5h.01M8.5 14h7"/>',
  star: '<path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.8z"/>',
  flag: '<path d="M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11"/>',
  link: '<path d="M14 4.5h5.5V10M19.5 4.5 11 13M17.5 14v4.5a1.5 1.5 0 0 1-1.5 1.5H6a1.5 1.5 0 0 1-1.5-1.5V8.5A1.5 1.5 0 0 1 6 7h4.5"/>',
  sparkle: '<path d="M12 3.5c.6 4.4 2.1 6 6.5 6.5-4.4.6-5.9 2.1-6.5 6.5-.6-4.4-2.1-5.9-6.5-6.5 4.4-.5 5.9-2.1 6.5-6.5z"/>',
  receipt: '<path d="M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  wrench: '<path d="M14.5 5.5a4 4 0 0 0 4.9 4.9L11 18.8a2 2 0 0 1-2.8-2.8L16.6 7.6z"/>',
};
export function icon(name, size = 20, stroke = 1.8) {
  return '<svg class="ic" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + stroke
    + '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (P[name] || P.sparkle) + '</svg>';
}
