import { TRANSLATIONS, type TranslationKey } from "@/i18n/translations";
import { useWorkspaceStore } from "@/stores/workspaceStore";

export function useT() {
  const locale = useWorkspaceStore((s) => s.locale);
  const dict = TRANSLATIONS[locale];
  return (key: TranslationKey): string => dict[key];
}
