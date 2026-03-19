/**
 * main.ts
 *
 * Bootstraps PrimeVue and other plugins then mounts the app.
 */

// Composables
import { createApp } from 'vue';

// Plugins
import { registerPlugins } from '@/plugins';

// Components
import App from './App.vue';

// Styles
import 'unfonts.css';
import './styles/tailwind.css';
import './styles/main.scss';

// Locales
import { useLocaleStore } from '@/stores/localeStore';

// Theme
import { useTheme } from '@/composables/useTheme';

// Create app
const app = createApp(App);
registerPlugins(app);

// Initialize locale store
const localeStore = useLocaleStore();
localeStore.initLocale();

// Initialize theme
const { initTheme } = useTheme();
initTheme();



app.mount('#app');
