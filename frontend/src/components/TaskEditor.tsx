// The task editor popout — the SAME window for creating (no taskId) and editing (taskId). Fields:
// title, description, tags (toggle chips). On create you also pick the project (its code forms the
// id); on edit the id is fixed and shown. Delete (edit mode) routes through the shared confirm.
//
// Draft lives in instance state and text inputs mutate it WITHOUT calling update() — so typing never
// re-renders the field (Nano recreates DOM on update(), which would drop focus/caret). update() is
// only called for discrete changes (toggling a tag, showing an error).

import Nano, { Component, h } from "nano-jsx";
import { taskApi } from "../api";
import { contrastInk, projectCodes, tagsList, taskById, projectOf, type Task } from "../model";
import { askConfirm, closePopup, openPopup } from "../ui";
import { Modal, presentIf } from "./shared_widgets";
import { dbFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";

interface TaskEditorProps { taskId?: string; }

export class TaskEditor extends Component<TaskEditorProps> {
    private draft: { title: string; description: string; tags: string[]; projectCode: string };
    private error: string | null = null;

    constructor(props: TaskEditorProps) {
        super(props);
        const existing: Task | null = props.taskId ? taskById(props.taskId) : null;
        this.draft = {
            title: existing?.title ?? "",
            description: existing?.description ?? "",
            tags: [...(existing?.tags ?? [])],
            projectCode: projectCodes()[0] ?? "",
        };
        bindFrames(this, [dbFrame]);
    }

    private isEdit(): boolean {
        return !!this.props.taskId && !!taskById(this.props.taskId);
    }

    private toggleTag(tagId: string): void {
        this.draft.tags = this.draft.tags.includes(tagId)
            ? this.draft.tags.filter((id) => id !== tagId)
            : [...this.draft.tags, tagId];
        this.update();
    }

    private async save(): Promise<void> {
        const { title, description, tags, projectCode } = this.draft;
        const error = this.isEdit()
            ? await taskApi.update(this.props.taskId!, title, description, tags)
            : await taskApi.create(projectCode, title, description, tags);
        if (error) { this.error = error; this.update(); return; }
        closePopup();
    }

    private confirmDelete(): void {
        const id = this.props.taskId!;
        askConfirm({
            message: `Delete task ${id}? This cannot be undone.`,
            confirmLabel: "Delete it",
            action: async () => { await taskApi.delete(id); closePopup(); },
        });
    }

    override render() {
        const editing = this.isEdit();
        const codes = projectCodes();
        const canSave = editing || (this.draft.projectCode !== "");

        return (
            <Modal title={editing ? `Edit ${this.props.taskId}` : "New task"} onClose={closePopup}>
                {!editing && codes.length === 0
                    ? <div class="form-error">
                          You need a project first (the task id comes from it).{" "}
                          <button class="linkish" onClick={() => openPopup({ kind: "projects" })}>
                              Make one →
                          </button>
                      </div>
                    : null}

                <label class="field-label">Title</label>
                <input class="text-input" type="text" value={this.draft.title}
                       placeholder="Do the thing"
                       onInput={(e: any) => { this.draft.title = e.target.value; }} />

                <label class="field-label">Description</label>
                <textarea class="area-input" placeholder="What's the thing?"
                          onInput={(e: any) => { this.draft.description = e.target.value; }}>
                    {this.draft.description}
                </textarea>

                {editing
                    ? <div class="field-label">Project&nbsp;
                          <span class="card-id">#{projectOf(this.props.taskId!)}-{this.props.taskId!.split("-")[1]}</span>
                      </div>
                    : <div>
                          <label class="field-label">Project</label>
                          <select class="select-input"
                                  onChange={(e: any) => { this.draft.projectCode = e.target.value; }}>
                              {codes.map((code) => (
                                  <option value={code} selected={presentIf(code === this.draft.projectCode)}>
                                      {code}
                                  </option>
                              ))}
                          </select>
                      </div>}

                <label class="field-label">Tags</label>
                <div class="tag-picker">
                    {tagsList().length === 0
                        ? <span class="muted">no tags yet</span>
                        : tagsList().map((tag) => {
                              const on = this.draft.tags.includes(tag.id);
                              return <button class={on ? "tag-chip pick on" : "tag-chip pick off"}
                                             style={on ? `background:${tag.color}; color:${contrastInk(tag.color)}` : ""}
                                             onClick={() => this.toggleTag(tag.id)}>
                                  {on ? "✓ " : ""}{tag.name}
                              </button>;
                          })}
                </div>

                {this.error ? <div class="form-error">{this.error}</div> : null}

                <div class="modal-buttons editor-buttons">
                    {editing
                        ? <button class="crayon-btn danger" onClick={() => this.confirmDelete()}>🗑️ Delete</button>
                        : null}
                    <button class="crayon-btn save" disabled={presentIf(!canSave)}
                            onClick={() => void this.save()}>
                        {editing ? "Save" : "Create"}
                    </button>
                </div>
            </Modal>
        );
    }
}
