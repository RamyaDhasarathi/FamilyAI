// The FamilyOS design is English, left-to-right. Declaring the app LTR-only
// keeps the layout intact even when a phone has the "Force RTL layout
// direction" developer option on (the Xiaomi test device does).
const { withAndroidManifest } = require('expo/config-plugins');

module.exports = function withLtrOnly(config) {
  return withAndroidManifest(config, (cfg) => {
    const app = cfg.modResults.manifest.application?.[0];
    if (app) app.$['android:supportsRtl'] = 'false';
    return cfg;
  });
};
