import { registerRootComponent } from 'expo';
// The collecting layer's background task must be defined before anything else runs (expo-task-manager).
import './src/familyos/services/collectTask';

import App from './App';

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
