// The Tags, Projects, and Assignee popouts. Each editable ROW is its own class component so its draft
// (and the text input's focus/caret) survives the list re-rendering when the DB frame changes. Same
// draft discipline as the task editor: text inputs mutate the draft without calling update().

import Nano, { Component, h } from "nano-jsx";
import { assigneeApi, projectApi, tagApi } from "../api";
import { assignee, allTasks, contrastInk, firstInitial, projectCodes, tagsList, type Tag } from "../model";
import { askConfirm, closePopup } from "../ui";
import { Modal, presentIf } from "./shared_widgets";
import { dbFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";

// ================================================================== Tags
class TagRow extends Component<{ tag: Tag }> {
    private draft: { name: string; color: string };
    private error: string | null = null;
    constructor(props: { tag: Tag }) {
        super(props);
        this.draft = { name: props.tag.name, color: props.tag.color };
    }
    private async save() {
        this.error = await tagApi.update(this.props.tag.id, this.draft.name, this.draft.color);
        this.update();
    }
    private confirmDelete() {
        askConfirm({
            message: `Delete tag "${this.props.tag.name}"? It will be removed from every task that has it.`,
            confirmLabel: "Delete tag",
            action: () => { void tagApi.delete(this.props.tag.id); },
        });
    }
    override render() {
        return (
            <div class="list-row">
                <input type="color" class="swatch" value={this.draft.color}
                       onInput={(e: any) => { this.draft.color = e.target.value; }} />
                <input type="text" class="text-input grow" value={this.draft.name}
                       onInput={(e: any) => { this.draft.name = e.target.value; }} />
                <button class="crayon-btn" onClick={() => void this.save()}>Save</button>
                <button class="crayon-btn danger" title="delete tag"
                        onClick={() => this.confirmDelete()}>🗑️</button>
                {this.error ? <div class="form-error">{this.error}</div> : null}
            </div>
        );
    }
}

class NewTagForm extends Component {
    private draft = { name: "", color: "#ff5c5c" };
    private error: string | null = null;
    private async add() {
        this.error = await tagApi.create(this.draft.name, this.draft.color);
        if (!this.error) this.draft = { name: "", color: "#ff5c5c" };
        this.update();
    }
    override render() {
        return (
            <div class="list-row new">
                <input type="color" class="swatch" value={this.draft.color}
                       onInput={(e: any) => { this.draft.color = e.target.value; }} />
                <input type="text" class="text-input grow" placeholder="new tag name"
                       value={this.draft.name}
                       onInput={(e: any) => { this.draft.name = e.target.value; }} />
                <button class="crayon-btn save" onClick={() => void this.add()}>＋ Add</button>
                {this.error ? <div class="form-error">{this.error}</div> : null}
            </div>
        );
    }
}

export class TagsManager extends Component {
    constructor(props: any) { super(props); bindFrames(this, [dbFrame]); }
    override render() {
        const tags = tagsList();
        return (
            <Modal title="🏷️ Tags" onClose={closePopup}>
                {tags.length === 0 ? <div class="muted">No tags yet — add one below.</div> : null}
                {tags.map((tag) => <TagRow tag={tag} />)}
                <div class="list-divider">new tag</div>
                <NewTagForm />
            </Modal>
        );
    }
}

// ================================================================== Projects
class ProjectRow extends Component<{ code: string }> {
    private draft: { newCode: string };
    private error: string | null = null;
    constructor(props: { code: string }) {
        super(props);
        this.draft = { newCode: props.code };
    }
    private async rename() {
        if (this.draft.newCode.toUpperCase() === this.props.code) return;
        this.error = await projectApi.rename(this.props.code, this.draft.newCode);
        this.update();
    }
    private confirmDelete() {
        const count = allTasks().filter((t) => t.id.startsWith(`${this.props.code}-`)).length;
        askConfirm({
            message: `Delete project ${this.props.code}? This DELETES all ${count} of its task(s) too — the id is hard-tied.`,
            confirmLabel: "Delete project + tasks",
            action: () => { void projectApi.delete(this.props.code); },
        });
    }
    override render() {
        const count = allTasks().filter((t) => t.id.startsWith(`${this.props.code}-`)).length;
        return (
            <div class="list-row">
                <input type="text" class="text-input code-input" maxLength={3} value={this.draft.newCode}
                       onInput={(e: any) => { this.draft.newCode = e.target.value; }} />
                <span class="grow muted">{count} task(s)</span>
                <button class="crayon-btn" onClick={() => void this.rename()}>Rename</button>
                <button class="crayon-btn danger" title="delete project"
                        onClick={() => this.confirmDelete()}>🗑️</button>
                {this.error ? <div class="form-error">{this.error}</div> : null}
            </div>
        );
    }
}

class NewProjectForm extends Component {
    private draft = { code: "" };
    private error: string | null = null;
    private async add() {
        this.error = await projectApi.create(this.draft.code);
        if (!this.error) this.draft = { code: "" };
        this.update();
    }
    override render() {
        return (
            <div class="list-row new">
                <input type="text" class="text-input code-input" maxLength={3} placeholder="ABC"
                       value={this.draft.code}
                       onInput={(e: any) => { this.draft.code = e.target.value; }} />
                <span class="grow muted">3 letters</span>
                <button class="crayon-btn save" onClick={() => void this.add()}>＋ Add</button>
                {this.error ? <div class="form-error">{this.error}</div> : null}
            </div>
        );
    }
}

export class ProjectsManager extends Component {
    constructor(props: any) { super(props); bindFrames(this, [dbFrame]); }
    override render() {
        const codes = projectCodes();
        return (
            <Modal title="📁 Projects" onClose={closePopup}>
                {codes.length === 0 ? <div class="muted">No projects yet — add one below.</div> : null}
                {codes.map((code) => <ProjectRow code={code} />)}
                <div class="list-divider">new project</div>
                <NewProjectForm />
            </Modal>
        );
    }
}

// ================================================================== Assignee (single user)
export class AssigneeEditor extends Component {
    private draft: { name: string; color: string };
    private error: string | null = null;
    constructor(props: any) {
        super(props);
        const current = assignee();
        this.draft = { name: current.name, color: current.color };
        bindFrames(this, [dbFrame]);
    }
    private async save() {
        this.error = await assigneeApi.set(this.draft.name, this.draft.color);
        if (!this.error) closePopup();
        else this.update();
    }
    override render() {
        return (
            <Modal title="🙂 Assignee" onClose={closePopup}>
                <div class="muted">Dzhira is single-user — this one person is on every task.</div>
                <div class="assignee-editor-row">
                    <span class="assignee-circle huge"
                          style={`background:${this.draft.color}; color:${contrastInk(this.draft.color)}`}>
                        {firstInitial(this.draft.name)}
                    </span>
                    <div class="grow">
                        <label class="field-label">Name</label>
                        <input type="text" class="text-input" value={this.draft.name}
                               onInput={(e: any) => { this.draft.name = e.target.value; this.update(); }} />
                        <label class="field-label">Circle color</label>
                        <input type="color" class="swatch big" value={this.draft.color}
                               onInput={(e: any) => { this.draft.color = e.target.value; this.update(); }} />
                    </div>
                </div>
                {this.error ? <div class="form-error">{this.error}</div> : null}
                <div class="modal-buttons editor-buttons">
                    <button class="crayon-btn save" onClick={() => void this.save()}>Save</button>
                </div>
            </Modal>
        );
    }
}
