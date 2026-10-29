// Development backends speak plain HTTP (http://localhost:8000 over
// `adb reverse`, or the Mac's LAN address), which Android refuses in release
// builds. Allow cleartext only when the configured backend itself is http://;
// an https:// backend, or none, keeps Android's default refusal.
const { withAndroidManifest } = require('expo/config-plugins');

module.exports = function withDevBackendHttp(config) {
  const api = process.env.EXPO_PUBLIC_FAMILYOS_API || '';
  if (!api.startsWith('http://')) return config;
  return withAndroidManifest(config, (cfg) => {
    const app = cfg.modResults.manifest.application?.[0];
    if (app) app.$['android:usesCleartextTraffic'] = 'true';
    return cfg;
  });
};
