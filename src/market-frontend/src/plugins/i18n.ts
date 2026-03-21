import { createI18n, type I18n } from 'vue-i18n';
import messages from '@/i18n';

const i18n: I18n = createI18n({
    legacy: false,
    locale: 'en', // This will be overwritten by the store
    fallbackLocale: 'en',
    messages,
});

export default i18n;
