import router from '../router';
import i18n from './i18n';
import { createPinia } from 'pinia';
import ToastService from 'primevue/toastservice';

// Types
import type { App } from 'vue';

// Plugins
import { primevue, primevueOptions } from './primevue';

export function registerPlugins(app: App) {
    app.use(primevue, primevueOptions);
    app.use(createPinia());
    app.use(i18n);
    app.use(router);
    app.use(ToastService);
}
