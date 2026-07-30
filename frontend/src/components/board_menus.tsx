// The board-view account menus: board switcher, new-board modal, invite modal, profile+members
// modal, and a shared invites list. These are API-driven (request/response), not websocket-synced.

import Nano, { Component, h } from "nano-jsx";
import { accountApi, boardsApi, invitesApi } from "../api";
import { authFrame, boardMetaFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { boardName, contrastInk, firstInitial, members, myRole, type Member } from "../model";
import { boardPath, navigate } from "../router";
import { askConfirm, closePopup, openPopup } from "../ui";
import { Modal } from "./shared_widgets";

function myUserId(): string {
    const user = authFrame.read("user");
    return user && typeof user === "object" ? user.id : "";
}

// ================================================================== invites list (reused)
export class InvitesList extends Component<{ onAccepted?: (boardName: string) => void }> {
    private invites: Array<{ id: string; board_name: string; inviter: string }> = [];
    private loading = true;

    override async didMount() { await this.reload(); }

    private async reload() {
        try { this.invites = (await invitesApi.mine()).invites; } catch { this.invites = []; }
        this.loading = false;
        this.update();
    }
    private async accept(invite: { id: string; board_name: string }) {
        await invitesApi.accept(invite.id);
        this.props.onAccepted?.(invite.board_name);
        await this.reload();
    }
    private async reject(id: string) { await invitesApi.reject(id); await this.reload(); }

    override render() {
        if (this.loading) return <div class="muted">loading invites…</div>;
        if (this.invites.length === 0) return <div class="muted">No invites available.</div>;
        return (
            <div class="invite-rows">
                {this.invites.map((inv) => (
                    <div class="list-row">
                        <span class="grow"><b>{inv.board_name}</b> <span class="muted">from {inv.inviter}</span></span>
                        <button class="crayon-btn save" onClick={() => void this.accept(inv)}>Accept</button>
                        <button class="crayon-btn danger" onClick={() => void this.reject(inv.id)}>Reject</button>
                    </div>
                ))}
            </div>
        );
    }
}

// ================================================================== board switcher (topbar)
export class BoardSwitcher extends Component {
    private open = false;
    private boards: Array<{ id: string; name: string; role: string }> = [];

    constructor(props: any) { super(props); bindFrames(this, [boardMetaFrame]); }

    private async toggle() {
        this.open = !this.open;
        if (this.open) { try { this.boards = (await boardsApi.list()).boards; } catch { /* keep */ } }
        this.update();
    }
    private go(name: string) { this.open = false; this.update(); navigate(boardPath(name)); }

    override render() {
        const ownedCount = this.boards.filter((b) => b.role === "owner").length;
        return (
            <div class="board-switcher">
                <button class="crayon-btn board-switcher-button" onClick={() => void this.toggle()}>
                    📋 {boardName() || "board"} ▾
                </button>
                {this.open ? <div class="dropdown-backdrop"
                                  onClick={() => { this.open = false; this.update(); }}></div> : null}
                {this.open ? (
                    <div class="dropdown">
                        <div class="dropdown-section-label">your boards</div>
                        {this.boards.map((b) => (
                            <button class={b.name === boardName() ? "dropdown-item active" : "dropdown-item"}
                                    onClick={() => this.go(b.name)}>
                                {b.name} <span class="muted">({b.role})</span>
                            </button>
                        ))}
                        <div class="dropdown-divider"></div>
                        <div class="dropdown-section-label">invites</div>
                        <InvitesList onAccepted={(name) => this.go(name)} />
                        <div class="dropdown-divider"></div>
                        {ownedCount < 2
                            ? <button class="crayon-btn save dropdown-new"
                                      onClick={() => { this.open = false; this.update(); openPopup({ kind: "newboard" }); }}>
                                  ＋ New board
                              </button>
                            : <div class="muted">You own the max of 2 boards.</div>}
                    </div>
                ) : null}
            </div>
        );
    }
}

// ================================================================== new-board modal
export class NewBoardModal extends Component {
    private draft = { name: "" };
    private error: string | null = null;

    private async create() {
        try {
            const { name } = await boardsApi.create(this.draft.name);
            closePopup();
            navigate(boardPath(name));
        } catch (e: any) { this.error = e.message; this.update(); }
    }
    override render() {
        return (
            <Modal title="＋ New board" onClose={closePopup}>
                <label class="field-label">Board name</label>
                <input class="text-input" placeholder="My Grand Plan"
                       onInput={(e: any) => { this.draft.name = e.target.value; }} />
                {this.error ? <div class="form-error">{this.error}</div> : null}
                <div class="modal-buttons editor-buttons">
                    <button class="crayon-btn" onClick={closePopup}>Cancel</button>
                    <button class="crayon-btn save" onClick={() => void this.create()}>Create</button>
                </div>
            </Modal>
        );
    }
}

// ================================================================== invite modal (generate invites)
export class InviteModal extends Component {
    private draft = { username: "" };
    private error: string | null = null;
    private pending: Array<{ id: string; invitee: string }> = [];

    override async didMount() { await this.reload(); }

    private async reload() {
        try { this.pending = (await boardsApi.boardInvites(boardName())).invites; } catch { this.pending = []; }
        this.update();
    }
    private async send() {
        this.error = await boardsApi.invite(this.draft.username);
        if (!this.error) { this.draft.username = ""; await this.reload(); } else { this.update(); }
    }
    private async withdraw(id: string) { await invitesApi.withdraw(id); await this.reload(); }

    override render() {
        return (
            <Modal title="✉️ Invite people" onClose={closePopup}>
                <label class="field-label">Invite by username</label>
                <div class="list-row new">
                    <input class="text-input grow" placeholder="exact username" value={this.draft.username}
                           onInput={(e: any) => { this.draft.username = e.target.value; }} />
                    <button class="crayon-btn save" onClick={() => void this.send()}>Invite</button>
                </div>
                {this.error ? <div class="form-error">{this.error}</div> : null}
                <div class="list-divider">pending invites</div>
                {this.pending.length === 0 ? <div class="muted">None outstanding.</div>
                    : this.pending.map((inv) => (
                        <div class="list-row">
                            <span class="grow">{inv.invitee}</span>
                            <button class="crayon-btn danger" onClick={() => void this.withdraw(inv.id)}>Withdraw</button>
                        </div>))}
            </Modal>
        );
    }
}

// ================================================================== profile + members modal
export class ProfileMembers extends Component {
    private nameDraft = "";
    private pw = { current: "", next: "", confirm: "" };
    private nameMsg: string | null = null;
    private pwMsg: string | null = null;

    constructor(props: any) {
        super(props);
        const user = authFrame.read("user");
        this.nameDraft = user ? user.username : "";
        bindFrames(this, [boardMetaFrame, authFrame]);       // members + my identity are live-ish
    }

    private async saveName() {
        this.nameMsg = await accountApi.rename(this.nameDraft);
        if (!this.nameMsg) {
            try { authFrame.write("user", (await (await fetch("/api/auth/me")).json()).user); } catch { /* ignore */ }
            this.nameMsg = "saved ✓";
        }
        this.update();
    }
    private async savePassword() {
        if (this.pw.next !== this.pw.confirm) { this.pwMsg = "New passwords don't match."; this.update(); return; }
        this.pwMsg = await accountApi.changePassword(this.pw.current, this.pw.next);
        if (!this.pwMsg) { this.pw = { current: "", next: "", confirm: "" }; this.pwMsg = "changed ✓"; }
        this.update();
    }
    private kick(member: Member) {
        askConfirm({
            message: `Kick ${member.username} from this board? They lose access and drop off every task.`,
            confirmLabel: "Kick", action: () => { void boardsApi.kick(member.id); },
        });
    }
    private makeOwner(member: Member) {
        askConfirm({
            message: `Make ${member.username} the owner? You become a regular member.`,
            confirmLabel: "Transfer", action: () => { void boardsApi.transfer(member.id); },
        });
    }
    private deleteBoard() {
        askConfirm({
            message: "Delete this whole board and everything on it? This cannot be undone.",
            confirmLabel: "Delete board",
            action: async () => {
                await boardsApi.delete((boardMetaFrame.read("id") as string) || "");
                closePopup();
                try {
                    const { boards } = await boardsApi.list();
                    navigate(boards.length ? boardPath(boards[0].name) : "/new");
                } catch { navigate("/new"); }
            },
        });
    }

    override render() {
        const amOwner = myRole() === "owner";
        const meId = myUserId();
        return (
            <Modal title="🙂 Profile & members" onClose={closePopup} wide>
                <label class="field-label">Your username</label>
                <div class="list-row new">
                    <input class="text-input grow" value={this.nameDraft}
                           onInput={(e: any) => { this.nameDraft = e.target.value; }} />
                    <button class="crayon-btn save" onClick={() => void this.saveName()}>Save</button>
                </div>
                {this.nameMsg ? <div class={this.nameMsg.includes("✓") ? "muted" : "form-error"}>{this.nameMsg}</div> : null}

                <label class="field-label">Change password</label>
                <input class="text-input" type="password" placeholder="current password"
                       onInput={(e: any) => { this.pw.current = e.target.value; }} />
                <input class="text-input" type="password" placeholder="new password"
                       onInput={(e: any) => { this.pw.next = e.target.value; }} />
                <input class="text-input" type="password" placeholder="confirm new password"
                       onInput={(e: any) => { this.pw.confirm = e.target.value; }} />
                <div class="modal-buttons editor-buttons">
                    <button class="crayon-btn save" onClick={() => void this.savePassword()}>Change password</button>
                </div>
                {this.pwMsg ? <div class={this.pwMsg.includes("✓") ? "muted" : "form-error"}>{this.pwMsg}</div> : null}

                <div class="list-divider">members</div>
                {members().map((member) => (
                    <div class="list-row">
                        <span class="assignee-circle" style={`background-color:${member.color}; color:${contrastInk(member.color)}`}>
                            {firstInitial(member.username)}
                        </span>
                        <span class="grow">{member.username}{member.id === meId ? " (you)" : ""}
                            <span class="muted"> · {member.role}</span></span>
                        {amOwner && member.id !== meId
                            ? [<button class="crayon-btn" onClick={() => this.makeOwner(member)}>Make owner</button>,
                               <button class="crayon-btn danger" onClick={() => this.kick(member)}>Kick</button>]
                            : null}
                    </div>
                ))}

                {amOwner ? (
                    <div class="danger-zone">
                        <div class="list-divider">danger zone</div>
                        <button class="crayon-btn danger" onClick={() => this.deleteBoard()}>🗑️ Delete this board</button>
                    </div>
                ) : null}
            </Modal>
        );
    }
}
