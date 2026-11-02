// Glowing orb in an agent colour (Today rows, timeline dots).
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

export function GlowOrb({ color, size = 28 }: { color: string; size?: number }) {
  const id = `g${color.replace('#', '')}${size}`;
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40" accessible={false}>
      <Defs>
        <RadialGradient id={id} cx="38%" cy="34%" r="70%">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.85} />
          <Stop offset="0.28" stopColor={color} stopOpacity={0.95} />
          <Stop offset="0.85" stopColor={color} stopOpacity={0.45} />
          <Stop offset="1" stopColor={color} stopOpacity={0.1} />
        </RadialGradient>
        <RadialGradient id={`${id}h`} cx="50%" cy="50%" r="50%">
          <Stop offset="0.55" stopColor={color} stopOpacity={0.35} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={20} cy={20} r={20} fill={`url(#${id}h)`} />
      <Circle cx={20} cy={20} r={13} fill={`url(#${id})`} />
    </Svg>
  );
}

/** Small glowing timeline dot. */
export function GlowDot({ color, size = 8 }: { color: string; size?: number }) {
  return (
    <Svg width={size * 2.2} height={size * 2.2} viewBox="0 0 22 22" accessible={false}>
      <Defs>
        <RadialGradient id={`d${color.replace('#', '')}`} cx="50%" cy="50%" r="50%">
          <Stop offset="0.35" stopColor={color} stopOpacity={0.5} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={11} cy={11} r={11} fill={`url(#d${color.replace('#', '')})`} />
      <Circle cx={11} cy={11} r={4} fill={color} />
    </Svg>
  );
}
