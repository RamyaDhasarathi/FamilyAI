// URL slug for a profile-menu row ("Privacy and data" → "privacy-and-data").
export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
