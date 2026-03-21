import { ref, watch } from 'vue';

const STORAGE_KEY = 'app-theme';
const DARK_CLASS = 'app-dark';

const isDark = ref(false);
let initialized = false;

const applyThemeClass = (dark: boolean) => {
    document.documentElement.classList.toggle(DARK_CLASS, dark);
};

const detectInitialTheme = (): boolean => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark') return true;
    if (saved === 'light') return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
};

const initTheme = () => {
    if (initialized) return;
    initialized = true;

    isDark.value = detectInitialTheme();
    applyThemeClass(isDark.value);

    watch(isDark, (dark) => {
        applyThemeClass(dark);
        localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light');
    });
};

const setTheme = (dark: boolean) => {
    isDark.value = dark;
};

const toggleTheme = () => {
    isDark.value = !isDark.value;
};

export const useTheme = () => ({
    isDark,
    initTheme,
    setTheme,
    toggleTheme,
});

export default useTheme;
