// Interactive core maths (AGENT_CORE_AND_FAMILY.md §3), all worklets.
//
// Orientation is a unit quaternion q = [w, x, y, z] mapping the crystal's
// model space to view space (x right, y up, z towards the viewer). Every
// rotation is applied by PRE-multiplying a small rotation expressed in view
// space: q ← Δ(axis, angle) · q. That way the idle spin, a finger drag and a
// flick's momentum all act about screen-fixed axes and simply add up.

/** The idle spin: 4 turns per 72 s ambient loop, as before (rad/s). */
export const IDLE_SPEED = (4 * 2 * Math.PI) / 72;
/** The old fixed tilt about X, now baked into the starting orientation. */
const IDLE_TILT = 0.35;
/**
 * View-space axis of the idle spin. The old pipeline was R = Rx(tilt)·Ry(θ);
 * advancing θ equals rotating about Rx(tilt)·ŷ = (0, cos t, sin t) in view space.
 */
export const IDLE_AXIS = [0, Math.cos(IDLE_TILT), Math.sin(IDLE_TILT)];
/** Starting orientation: the old tilt, no spin. */
export const START_ORIENT = [Math.cos(IDLE_TILT / 2), Math.sin(IDLE_TILT / 2), 0, 0];

/** Jelly spring for the squash (§3.3: damping 7, stiffness 180, mass 1). */
export const JELLY_SPRING = { damping: 7, stiffness: 180, mass: 1 };
/** Fastest flick, about 4 full turns per second (§3.4). */
export const MAX_SPIN = 4 * 2 * Math.PI;
/** Momentum friction: ω *= exp(−FRICTION·dt), frame-rate independent. */
export const FRICTION = 2.8;
/** Under Reduce Motion a flick stops within ~0.3 s. */
export const FRICTION_REDUCED = 15;

export function qMul(a: number[], b: number[]) {
  'worklet';
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}

/** Rotation of `angle` radians about a (not necessarily unit) axis. */
export function qAxisAngle(ax: number, ay: number, az: number, angle: number) {
  'worklet';
  const l = Math.hypot(ax, ay, az);
  if (l < 1e-9 || Math.abs(angle) < 1e-9) return [1, 0, 0, 0];
  const s = Math.sin(angle / 2) / l;
  return [Math.cos(angle / 2), ax * s, ay * s, az * s];
}

export function qNormalize(q: number[]) {
  'worklet';
  const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  return [q[0] / l, q[1] / l, q[2] / l, q[3] / l];
}

/** Rotate q by `angle` about a view-space axis (pre-multiplied). */
export function qRotateView(q: number[], ax: number, ay: number, az: number, angle: number) {
  'worklet';
  return qNormalize(qMul(qAxisAngle(ax, ay, az, angle), q));
}

/** Row-major 3×3 matrix: view = M · model. */
export function qToMat(q: number[]) {
  'worklet';
  const [w, x, y, z] = q;
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ];
}

/** The old angle pair as a matrix (R = Rx(tilt)·Ry(rotY)), for mini gems. */
export function matFromAngles(rotY: number, tiltX: number) {
  'worklet';
  const cY = Math.cos(rotY);
  const sY = Math.sin(rotY);
  const cX = Math.cos(tiltX);
  const sX = Math.sin(tiltX);
  return [cY, 0, sY, -sX * -sY, cX, -sX * cY, -sY * cX, sX, cX * cY];
}

/** Camera distance in model radii; must match the renderer's projection. */
const CAM = 4.2;

/**
 * Where a screen point lands on the crystal (§3.3 step 1). The renderer
 * projects a view-space point p on screen as c + p.xy · R · CAM / (CAM − p.z)
 * (y flipped), so the pixel (u, v) in radii sees the ray
 *   p(k) = (u·k, v·k, CAM·(1 − k)),  k = (CAM − z) / CAM.
 * Intersecting |p| = 1 gives a quadratic in k; the smaller root is the front
 * hit. If the ray misses (a tap on the rim of the hit area) the nearest
 * silhouette point is used. Returns view-space and model-space unit vectors.
 */
export function hitCrystal(sx: number, sy: number, cx: number, cy: number, R: number, M: number[]) {
  'worklet';
  const u = (sx - cx) / R;
  const v = -(sy - cy) / R;
  const a = u * u + v * v + CAM * CAM;
  const b = -2 * CAM * CAM;
  const c = CAM * CAM - 1;
  const disc = b * b - 4 * a * c;
  let hx: number;
  let hy: number;
  let hz: number;
  if (disc >= 0) {
    const k = (-b - Math.sqrt(disc)) / (2 * a);
    hx = u * k;
    hy = v * k;
    hz = CAM * (1 - k);
  } else {
    const l = Math.hypot(u, v) || 1;
    hx = u / l;
    hy = v / l;
    hz = 0;
  }
  const l = Math.hypot(hx, hy, hz) || 1;
  hx /= l;
  hy /= l;
  hz /= l;
  // Model space = Mᵀ · view (M is a rotation, so its inverse is its transpose).
  return {
    view: [hx, hy, hz],
    model: [M[0] * hx + M[3] * hy + M[6] * hz, M[1] * hx + M[4] * hy + M[7] * hz, M[2] * hx + M[5] * hy + M[8] * hz],
  };
}
