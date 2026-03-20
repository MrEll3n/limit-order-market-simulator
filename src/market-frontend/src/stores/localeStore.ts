import { defineStore } from 'pinia';
import { ref } from 'vue';
import i18n from '@/plugins/i18n';
import messages from '@/i18n';

const STORAGE_KEY = 'app-locale';
const DEFAULT_LOCALE = 'en';

export const useLocaleStore = defineStore('locale', () => {
    const locale = ref<string>(DEFAULT_LOCALE);
    const availableLocales = Object.keys(messages);

    /**
     * Mapping locales to flags
     */
    const localeToFlagMap: Record<string, string> = {
        cs: 'cz',
        en: 'gb',
    };

    /**
     * Sets the application's locale.
     * @param {string} newLocale - The new locale code (e.g., 'en', 'cs').
     */
    function setLocale(newLocale: string) {
        if (!availableLocales.includes(newLocale)) {
            console.warn(`Locale "${newLocale}" is not available. Falling back to default.`);
            newLocale = DEFAULT_LOCALE;
        }

        locale.value = newLocale;
        if (typeof i18n.global.locale === 'string') {
            i18n.global.locale = newLocale;
        } else {
            i18n.global.locale.value = newLocale;
        }

        localStorage.setItem(STORAGE_KEY, newLocale);
    }

    /**
     * Toggle throughout all locales in availableLoacles list
     */
    function toggleLocale() {
        // find locale and return its index
        const index: number = availableLocales.findIndex((current: string) => current == locale.value);

        const nextLocale = availableLocales[(index + 1) % availableLocales.length];

        setLocale(nextLocale);
    }

    /**
     * Return flag icon representation of current locale
     * @returns
     */
    function getFlag() {
        return `fi fi-${localeToFlagMap[locale.value]}`;
    }

    /**
     * Initializes the locale from localStorage or sets the default.
     */
    function initLocale() {
        const savedLocale = localStorage.getItem(STORAGE_KEY);
        setLocale(savedLocale || DEFAULT_LOCALE);
    }

    return {
        locale,
        availableLocales,
        setLocale,
        toggleLocale,
        getFlag,
        localeToFlagMap,
        initLocale,
    };
});
