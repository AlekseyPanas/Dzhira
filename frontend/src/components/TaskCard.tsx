// One task card: bold title, truncated description, colored tag chips, the #PROJ-NNN id in a corner,
// the assignee initial-circle, and a trash icon. Clicking the card (not the trash) opens the editor;
// the trash asks for confirmation, then deletes. Drag wiring is added in the drag-and-drop step.

import Nano, { h } from "nano-jsx";
import { taskApi } from "../api";
import { consumeDragClick } from "../drag_controller";
import { contrastInk, deadlineStatus, firstInitial, formatDeadline, membersById, projectColor, projectOf, tagsById, type Task } from "../model";
import { askConfirm, openPopup } from "../ui";
import { truncate } from "./shared_widgets";

export const TaskCard = (props: { task: Task }) => {
    const task = props.task;
    const tagMap = tagsById();
    const memberMap = membersById();
    const projectHue = projectColor(projectOf(task.id));    // the card's left stripe + id badge color
    const dueStatus = deadlineStatus(task.deadline);        // "past" | "soon" | "later" | null

    const onDelete = (event: Event) => {
        event.stopPropagation();                            // don't also open the editor
        askConfirm({
            message: `Delete task ${task.id} — "${truncate(task.title, 40)}"? This cannot be undone.`,
            confirmLabel: "Delete it",
            action: () => { void taskApi.delete(task.id); },
        });
    };

    const onCardClick = () => {
        if (consumeDragClick()) return;                     // a drag just ended — don't open editor
        openPopup({ kind: "task", taskId: task.id });
    };

    return (
        <div class="task-card" data-task-id={task.id} data-status={task.status} onClick={onCardClick}>
            <div class="card-stripe" title={projectOf(task.id)} style={`background-color:${projectHue}`}></div>
            <button class="card-trash" title="delete task" onClick={onDelete}>🗑️</button>
            <div class="card-title">{task.title || "(untitled)"}</div>
            {task.description
                ? <div class="card-desc">{truncate(task.description, 90)}</div>
                : null}
            <div class="card-footer">
                <div class="card-tags">
                    {dueStatus
                        ? <span class={`deadline-chip ${dueStatus}`} title={`due ${task.deadline}`}>
                              📅 {formatDeadline(task.deadline!)}
                          </span>
                        : null}
                    {task.tags.map((tagId) => {
                        const tag = tagMap[tagId];
                        if (!tag) return null;
                        return <span class="tag-chip" style={`background-color:${tag.color}; color:${contrastInk(tag.color)}`}>
                            {tag.name}
                        </span>;
                    })}
                </div>
                <div class="card-meta">
                    <span class="card-id" style={`background-color:${projectHue}; color:${contrastInk(projectHue)}`}>#{projectOf(task.id)}-{task.id.split("-")[1]}</span>
                    <span class="assignee-stack">
                        {task.assignees.map((uid) => {
                            const member = memberMap[uid];
                            if (!member) return null;
                            return <span class="assignee-circle small" title={member.username}
                                         style={`background-color:${member.color}; color:${contrastInk(member.color)}`}>
                                {firstInitial(member.username)}
                            </span>;
                        })}
                    </span>
                </div>
            </div>
        </div>
    );
};
