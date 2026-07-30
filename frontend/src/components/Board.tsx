// The Kanban board: a horizontal row of status columns, each holding its tasks (sorted by order).
// Re-renders whenever the DB frame changes (bindFrames). Columns can be renamed inline, reordered
// with the ← → arrows, and deleted (their tasks reassign to the nearest column); a board always keeps
// at least one column. Cards are dragged by the drag controller; task create is the topbar + button.

import Nano, { Component, h } from "nano-jsx";
import { columnApi } from "../api";
import { boardFrame, boardMetaFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { columnsSorted, tasksInColumn, type Column } from "../model";
import { askConfirm } from "../ui";
import { presentIf } from "./shared_widgets";
import { TaskCard } from "./TaskCard";

interface ColumnProps { column: Column; isFirst: boolean; isLast: boolean; isOnly: boolean; }

class ColumnView extends Component<ColumnProps> {
    private editingName = false;
    private nameDraft = "";

    private startRename() {
        this.editingName = true;
        this.nameDraft = this.props.column.name;
        this.update();
    }
    private commitRename() {
        this.editingName = false;
        void columnApi.rename(this.props.column.id, this.nameDraft);   // re-renders via the socket
        this.update();
    }
    private cancelRename() { this.editingName = false; this.update(); }

    private confirmDelete() {
        askConfirm({
            message: `Delete column "${this.props.column.name}"? Its tasks move to the nearest column.`,
            confirmLabel: "Delete column",
            action: () => { void columnApi.delete(this.props.column.id); },
        });
    }

    override render() {
        const { column, isFirst, isLast, isOnly } = this.props;
        const tasks = tasksInColumn(column.id);
        return (
            <div class="board-column">
                <div class="column-header">
                    <div class="column-arrows">
                        <button class="mini-btn" title="move left" disabled={presentIf(isFirst)}
                                onClick={() => void columnApi.move(column.id, "left")}>←</button>
                        <button class="mini-btn" title="move right" disabled={presentIf(isLast)}
                                onClick={() => void columnApi.move(column.id, "right")}>→</button>
                    </div>
                    {this.editingName
                        ? <input class="column-name-input grow" value={this.nameDraft}
                                 onInput={(e: any) => { this.nameDraft = e.target.value; }}
                                 onKeyDown={(e: any) => {
                                     if (e.key === "Enter") this.commitRename();
                                     if (e.key === "Escape") this.cancelRename();
                                 }} />
                        : <span class="column-name grow" title="rename"
                                onClick={() => this.startRename()}>{column.name}</span>}
                    {this.editingName
                        ? <button class="mini-btn" title="save name" onClick={() => this.commitRename()}>✓</button>
                        : <button class="mini-btn" title="rename" onClick={() => this.startRename()}>✎</button>}
                    <button class="mini-btn danger" title={isOnly ? "a board needs one column" : "delete column"}
                            disabled={presentIf(isOnly)} onClick={() => this.confirmDelete()}>🗑️</button>
                    <span class="column-count">{tasks.length}</span>
                </div>
                <div class="column-tasks" data-column-id={column.id}>
                    {tasks.length === 0
                        ? <div class="column-empty">no tasks — drag one here</div>
                        : tasks.map((task) => <TaskCard task={task} />)}
                </div>
            </div>
        );
    }
}

export class Board extends Component {
    constructor(props: any) {
        super(props);
        bindFrames(this, [boardFrame, boardMetaFrame]);   // re-render on content AND member changes
    }

    override render() {
        const columns = columnsSorted();
        return (
            <div class="board">
                {columns.length === 0
                    ? <div class="board-empty">No columns yet. Add one to get started →</div>
                    : columns.map((column, index) => (
                          <ColumnView column={column} isFirst={index === 0}
                                      isLast={index === columns.length - 1}
                                      isOnly={columns.length === 1} />))}
                <button class="add-column" title="add a status column"
                        onClick={() => void columnApi.create("new column")}>
                    ＋<br />column
                </button>
            </div>
        );
    }
}
