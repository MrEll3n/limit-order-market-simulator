import PrimeVue from 'primevue/config';
import Aura from '@primeuix/themes/aura';
import 'primeicons/primeicons.css';
import '../styles/layers.css';

export const primevue = PrimeVue;

export const primevueOptions = {
    theme: {
        preset: Aura,
        options: {
            darkModeSelector: '.app-dark',
            cssLayer: {
                name: 'primevue',
                order: 'tailwind-theme, tailwind-reset, primevue, app-overrides, tailwind-utilities',
            },
        },
    },
};