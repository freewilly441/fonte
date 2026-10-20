import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.aethermark.fonte',
  appName: 'Fonte',
  webDir: 'www',
  server: {
    androidScheme: 'https',
    allowNavigation: ['127.0.0.1', 'localhost']
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      backgroundColor: '#1e1e1e',
      showSpinner: true,
      spinnerColor: '#ffffff'
    }
  }
};

export default config;
