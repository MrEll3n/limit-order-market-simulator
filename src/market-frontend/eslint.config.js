import vuetify from "eslint-config-vuetify";
import eslintConfigPrettier from "eslint-config-prettier/flat";

export default [...vuetify({
    ts: true,
    rules: {
        "no-console": "warn",
        "vue/component-name-in-template-casing": ["error", "PascalCase"],
        "@typescript-eslint/no-unused-vars": "error",
    },
}), eslintConfigPrettier];
