import { Text, type TextProps } from 'react-native';
import { MAX_FONT_SCALE, type as typeScale } from '../theme/typography';

/** Text that scales with the system font size, capped at 1.3× (AGENT.md §11.4). */
export function AppText({ style, ...rest }: TextProps) {
  return <Text maxFontSizeMultiplier={MAX_FONT_SCALE} style={[typeScale.body, style]} {...rest} />;
}
