// The board topbar: wordmark, the board switcher, the create-task / manager buttons, an invite button,
// and the profile+members button (showing the current user).

import Nano, { Component, h } from "nano-jsx";
import { authApi } from "../api";
import { authFrame, boardMetaFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { contrastInk, firstInitial } from "../model";
import { navigate } from "../router";
import { openPopup } from "../ui";
import { BoardSwitcher } from "./board_menus";

export class Topbar extends Component {
    constructor(props: any) {
        super(props);
        bindFrames(this, [boardMetaFrame, authFrame]);
    }

    private async logout() {
        await authApi.logout();
        authFrame.write("user", null);
        navigate("/login");
    }

    override render() {
        const user = authFrame.read("user") || { username: "?", color: "#888" };
        return (
            <div class="topbar">
                <div class="brand">Dzhira <img class="brand-logo" src="/JIRABAD.png" alt="Dzhira logo" /></div>
                <BoardSwitcher />
                <div class="topbar-buttons">
                    <button class="crayon-btn big-add" onClick={() => openPopup({ kind: "task" })}>＋ New task</button>
                    <button class="crayon-btn" onClick={() => openPopup({ kind: "tags" })}>🏷️ Tags</button>
                    <button class="crayon-btn" onClick={() => openPopup({ kind: "projects" })}>📁 Projects</button>
                    <button class="crayon-btn" onClick={() => openPopup({ kind: "invite" })}>✉️ Invite</button>
                    <button class="assignee-button" title="profile & members"
                            onClick={() => openPopup({ kind: "profile" })}>
                        <span class="assignee-circle big"
                              style={`background-color:${user.color}; color:${contrastInk(user.color)}`}>
                            {firstInitial(user.username)}
                        </span>
                        <span class="assignee-name">{user.username}</span>
                    </button>
                    <button class="crayon-btn" title="log out" onClick={() => void this.logout()}>⎋ Logout</button>
                </div>
            </div>
        );
    }
}
