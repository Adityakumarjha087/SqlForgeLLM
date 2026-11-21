export type Theme = "system" | "light" | "dark";
export const THEME_KEY = "sqlforge-theme";

// Runs in <head> before first paint so a saved choice never flashes the other theme.
export const THEME_INIT_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export const THEME_COLORS = { light: "#faf9f5", dark: "#171716" } as const;

// <meta name="theme-color"> is declared per prefers-color-scheme, so it follows the OS and ignores
// the manual toggle. For a manual choice, point every tag at that theme's colour with media "all";
// for "system", put back the original media query and colour (remembered on first change).
export function syncThemeColor(theme: Theme) {
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
    meta.dataset.media ??= meta.media;
    meta.dataset.color ??= meta.content;
    if (theme === "system") {
      meta.media = meta.dataset.media;
      meta.content = meta.dataset.color;
    } else {
      meta.media = "all";
      meta.content = THEME_COLORS[theme];
    }
  });
}
