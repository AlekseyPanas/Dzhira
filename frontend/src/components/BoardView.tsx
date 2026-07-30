// The board page shell. Just the layout — the board's data/session (socket, members, access) is
// driven by board_session.ts off the route, so switching boards doesn't depend on component remounts.

import Nano, { Component, h } from "nano-jsx";
import { Board } from "./Board";
import { Popups } from "./Popups";
import { Topbar } from "./Topbar";

export class BoardView extends Component {
    override render() {
        // Theme selector is intentionally hidden for the showcase (paint is forced in client.tsx).
        // To re-enable it here: `import { ThemeSwitcher } from "./ThemeSwitcher"`, render <ThemeSwitcher/>
        // below <Popups/>, and drop the applyTheme("paint") force in client.tsx. Nothing was deleted.
        return (
            <div class="app">
                <Topbar />
                <Board />
                <Popups />
            </div>
        );
    }
}
