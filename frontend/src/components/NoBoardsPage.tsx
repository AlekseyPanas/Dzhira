// The /new page — shown when you have no boards (owned or shared): make one, or join via an invite.

import Nano, { Component, h } from "nano-jsx";
import { authApi, boardsApi } from "../api";
import { authFrame } from "../frames/shared_frames";
import { boardPath, navigate } from "../router";
import { InvitesList } from "./board_menus";

export class NoBoardsPage extends Component {
    private draft = { name: "" };
    private error: string | null = null;

    private async createBoard() {
        try {
            const { name } = await boardsApi.create(this.draft.name);
            navigate(boardPath(name));
        } catch (e: any) { this.error = e.message; this.update(); }
    }
    private async logout() {
        await authApi.logout();
        authFrame.write("user", null);
        navigate("/login");
    }

    override render() {
        return (
            <div class="auth-page">
                <div class="auth-card wide-card">
                    <div class="brand auth-brand">Dzhira <img class="brand-logo" src="/JIRABAD.png" alt="Dzhira logo" /></div>
                    <div class="auth-title">You have no boards yet</div>

                    <div class="new-section-label">make a new board</div>
                    <div class="list-row new">
                        <input class="text-input grow" placeholder="board name"
                               onInput={(e: any) => { this.draft.name = e.target.value; }}
                               onKeyDown={(e: any) => { if (e.key === "Enter") void this.createBoard(); }} />
                        <button class="crayon-btn save" onClick={() => void this.createBoard()}>Create & enter</button>
                    </div>
                    {this.error ? <div class="form-error">{this.error}</div> : null}

                    <div class="new-section-label">…or join one you were invited to</div>
                    <InvitesList onAccepted={(name) => navigate(boardPath(name))} />

                    <div class="auth-switch">
                        <button class="linkish" onClick={() => void this.logout()}>Log out</button>
                    </div>
                </div>
            </div>
        );
    }
}
