import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import zhHansTranslation from "./locales/zh-Hans.json";

const SUPPORTED_LANGUAGES = [
  "en",
  "de",
  "es",
  "fr",
  "ja",
  "pt",
  "zh-Hans",
] as const;

const normalizeLanguage = (lang?: string | null): string => {
  if (!lang) return "zh-Hans";

  if (
    SUPPORTED_LANGUAGES.includes(lang as (typeof SUPPORTED_LANGUAGES)[number])
  ) {
    return lang;
  }

  const lowerLang = lang.toLowerCase();

  if (["zh-hans", "zh-cn", "zh-sg"].includes(lowerLang)) {
    return "zh-Hans";
  }

  const baseLang = lang.split("-")[0];

  if (
    SUPPORTED_LANGUAGES.includes(
      baseLang as (typeof SUPPORTED_LANGUAGES)[number],
    )
  ) {
    return baseLang;
  }

  return "zh-Hans";
};

export const detectedLang = normalizeLanguage(
  localStorage.getItem("languagePreference") || "zh-Hans",
);

const i18n = i18next.createInstance();

// i18next hardcodes a Locize promotional message via console.info during init.
// Suppress it by temporarily replacing console.info for the synchronous init call.
const _consoleInfo = console.info.bind(console);
console.info = () => {};
i18n.use(initReactI18next).init({
  resources: {
    "zh-Hans": { translation: zhHansTranslation },
  },
  lng: detectedLang,
  fallbackLng: "zh-Hans",
  returnNull: false,
  returnEmptyString: false,
  interpolation: {
    escapeValue: false,
  },
});
console.info = _consoleInfo;

export async function loadLanguage(lang: string): Promise<void> {
  if (lang === "zh-Hans") return;
  if (i18n.hasResourceBundle(lang, "translation")) return;
  try {
    const messages = await import(`./locales/${lang}.json`);
    i18n.addResourceBundle(lang, "translation", messages.default);
  } catch {
    // Unknown locale — no bundle file exists. i18next's fallbackLng: "zh-Hans" takes over.
  }
}

export default i18n;
