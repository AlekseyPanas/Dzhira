// The topbar: the Dzhira wordmark, the create-task button, the manager buttons (Tags / Projects /
// Assignee), and the current assignee's initial-circle. Every button opens a popout via uiFrame.

import Nano, { Component, h } from "nano-jsx";
import { dbFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { assignee, contrastInk, firstInitial } from "../model";
import { openPopup } from "../ui";

export class Topbar extends Component {
    constructor(props: any) {
        super(props);
        bindFrames(this, [dbFrame]);                        // the assignee chip is live
    }

    override render() {
        const who = assignee();
        return (
            <div class="topbar">
                <div class="brand">Dzhira <span class="brand-crayon">🖍️</span></div>
                <div class="topbar-buttons">
                    <button class="crayon-btn big-add" title="new task"
                            onClick={() => openPopup({ kind: "task" })}>＋ New task</button>
                    <button class="crayon-btn" onClick={() => openPopup({ kind: "tags" })}>🏷️ Tags</button>
                    <button class="crayon-btn" onClick={() => openPopup({ kind: "projects" })}>📁 Projects</button>
                    <button class="assignee-button" title="edit assignee"
                            onClick={() => openPopup({ kind: "assignee" })}>
                        <span class="assignee-circle big"
                              style={`background:${who.color}; color:${contrastInk(who.color)}`}>
                            {firstInitial(who.name)}
                        </span>
                        <span class="assignee-name">{who.name}</span>
                    </button>
                </div>
            </div>
        );
    }
}
