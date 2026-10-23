// Date and greeting text (AGENT.md §6.3: real current date, greeting by time of day).
import { copy } from '../mocks/data';

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "Tuesday, October 20" — fixed English format so it matches the design on every device locale. */
export function formatLongDate(d: Date) {
  return `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function greetingFor(d: Date, name: string) {
  const h = d.getHours();
  const g = h < 12 ? copy.greeting.morning : h < 17 ? copy.greeting.afternoon : copy.greeting.evening;
  return `${g}, ${name}`;
}
