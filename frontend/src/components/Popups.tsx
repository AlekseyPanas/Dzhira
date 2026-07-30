// The single popout host: reads uiFrame and renders whichever popout is open, plus the confirm modal
// on top of everything (it can be raised from inside a popout — e.g. deleting a tag or kicking a user).

import Nano, { Component, h } from "nano-jsx";
import { uiFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { clearConfirm, closePopup, type PopupState } from "../ui";
import { ConfirmModal } from "./shared_widgets";
import { TaskEditor } from "./TaskEditor";
import { ProjectsManager, TagsManager } from "./managers";
import { InviteModal, NewBoardModal, ProfileMembers } from "./board_menus";

export class Popups extends Component {
    constructor(props: any) {
        super(props);
        bindFrames(this, [uiFrame]);
    }

    private renderPopup(popup: Exclude<PopupState, null>) {
        switch (popup.kind) {
            case "task": return <TaskEditor taskId={popup.taskId} />;
            case "tags": return <TagsManager />;
            case "projects": return <ProjectsManager />;
            case "invite": return <InviteModal />;
            case "profile": return <ProfileMembers />;
            case "newboard": return <NewBoardModal />;
            default: return null;
        }
    }

    override render() {
        const popup = uiFrame.read("popup") as PopupState;
        const confirm = uiFrame.read("confirm") as
            | null | { message: string; confirmLabel?: string; action: () => void };

        return (
            <div class="popups">
                {popup && typeof popup === "object" ? this.renderPopup(popup) : null}
                {confirm && typeof confirm === "object"
                    ? <ConfirmModal message={confirm.message} confirmLabel={confirm.confirmLabel}
                                    onConfirm={() => { confirm.action(); clearConfirm(); }}
                                    onCancel={clearConfirm} />
                    : null}
            </div>
        );
    }
}
