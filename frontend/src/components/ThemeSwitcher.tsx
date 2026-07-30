// The theme toggle, fixed in the bottom-right corner. Two buttons swap between the crisp crayon look
// and the horrific hand-painted look; the choice persists across reloads.

import Nano, { Component, h } from "nano-jsx";
import { applyTheme, getTheme, type ThemeName } from "../theme";

export class ThemeSwitcher extends Component {
    private pick(name: ThemeName): void {
        applyTheme(name);
        this.update();                                      // re-render to move the active highlight
    }

    override render() {
        const active = getTheme();
        const button = (name: ThemeName, label: string, title: string) => (
            <button class={active === name ? "theme-btn active" : "theme-btn"} title={title}
                    onClick={() => this.pick(name)}>{label}</button>
        );
        return (
            <div class="theme-switcher">
                <span class="theme-switcher-label">theme</span>
                {button("crisp", "✏️ crisp", "the crisp crayon look")}
                {button("paint", "🖌️ paint", "the horrific hand-painted look")}
            </div>
        );
    }
}
