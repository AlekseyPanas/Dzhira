// The /login and /create pages (one component, mode from the route). On success it sets the auth
// frame and routes on: to your first board, or /new if you have none.

import Nano, { Component, h } from "nano-jsx";
import { authApi, boardsApi } from "../api";
import { authFrame } from "../frames/shared_frames";
import { boardPath, currentRoute, navigate } from "../router";

// Module-level so the typed values survive the whole-app re-render when you toggle /login <-> /create
// (client.tsx rebuilds the page on route change; a fresh AuthPage reads this back). Cleared on success.
const authDraft = { username: "", password: "", confirm: "" };

export class AuthPage extends Component {
    private draft = authDraft;
    private error: string | null = null;
    private busy = false;

    private isCreate(): boolean { return currentRoute().name === "create"; }

    private async submit() {
        if (this.busy) return;
        if (this.isCreate() && this.draft.password !== this.draft.confirm) {
            this.error = "Passwords don't match."; this.update(); return;
        }
        this.busy = true; this.error = null; this.update();
        try {
            const call = this.isCreate() ? authApi.register : authApi.login;
            const { user } = await call(this.draft.username, this.draft.password);
            authDraft.username = authDraft.password = authDraft.confirm = "";   // don't keep creds around
            authFrame.write("user", user);
            const { boards } = await boardsApi.list();
            navigate(boards.length ? boardPath(boards[0].name) : "/new");
        } catch (e: any) {
            this.error = e.message; this.busy = false; this.update();
        }
    }

    override render() {
        const create = this.isCreate();
        return (
            <div class="auth-page">
                <div class="auth-card">
                    <div class="brand auth-brand">Dzhira <img class="brand-logo" src="/JIRABAD.png" alt="Dzhira logo" /></div>
                    <div class="auth-title">{create ? "Create account" : "Log in"}</div>
                    <input class="text-input" placeholder="username" value={this.draft.username}
                           onInput={(e: any) => { this.draft.username = e.target.value; }}
                           onKeyDown={(e: any) => { if (e.key === "Enter") void this.submit(); }} />
                    <input class="text-input" type="password" placeholder="password" value={this.draft.password}
                           onInput={(e: any) => { this.draft.password = e.target.value; }}
                           onKeyDown={(e: any) => { if (e.key === "Enter") void this.submit(); }} />
                    {create
                        ? <input class="text-input" type="password" placeholder="confirm password"
                                 value={this.draft.confirm}
                                 onInput={(e: any) => { this.draft.confirm = e.target.value; }}
                                 onKeyDown={(e: any) => { if (e.key === "Enter") void this.submit(); }} />
                        : null}
                    {this.error ? <div class="form-error">{this.error}</div> : null}
                    <button class="crayon-btn save auth-submit" onClick={() => void this.submit()}>
                        {this.busy ? "…" : (create ? "Create account" : "Log in")}
                    </button>
                    <div class="auth-switch">
                        {create
                            ? <span>Have an account? <button class="linkish" onClick={() => navigate("/login")}>Log in</button></span>
                            : <span>New here? <button class="linkish" onClick={() => navigate("/create")}>Create an account</button></span>}
                    </div>
                </div>
            </div>
        );
    }
}
