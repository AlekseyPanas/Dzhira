// Swappable visual themes. The CRISP theme is the base stylesheet (styles.scss); PAINT is an override
// layer (styles-paint.scss) scoped under :root[data-theme="paint"]. We just flip the attribute on
// <html> and persist the choice — no stylesheet swapping needed, both are compiled into one bundle.

export type ThemeName = "crisp" | "paint";

const STORAGE_KEY = "dzhira-theme";

export function getTheme(): ThemeName {
    // Paint is the default a first-timer lands on; only an explicit choice of crisp opts out.
    return localStorage.getItem(STORAGE_KEY) === "crisp" ? "crisp" : "paint";
}

export function applyTheme(name: ThemeName): void {
    document.documentElement.setAttribute("data-theme", name);
    localStorage.setItem(STORAGE_KEY, name);
}

/** Apply the saved theme (or the crisp default) — call once, before first render. */
export function initTheme(): void {
    applyTheme(getTheme());
}
