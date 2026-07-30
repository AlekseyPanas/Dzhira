// The per-user filter bar, pinned at the bottom. Toggle-chips for Assignee / Tags / Projects; the
// selection is YOUR saved view (persisted per board, synced via the mirror), so it survives reloads
// and reflects across your tabs. Filtering is a client-side view over the full task set.

import Nano, { Component, h } from "nano-jsx";
import { viewApi } from "../api";
import { authFrame, boardFrame, boardMetaFrame } from "../frames/shared_frames";
import { bindFrames } from "../frames/bind_frames";
import { contrastInk, filtersActive, firstInitial, members, myView, projects, tagsList, UNASSIGNED, type View } from "../model";

export class FilterBar extends Component {
    constructor(props: any) {
        super(props);
        bindFrames(this, [boardFrame, boardMetaFrame, authFrame]);
    }

    private toggle(category: keyof View, value: string) {
        const view = myView();
        const list = view[category];
        const next = list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
        const updated: View = { ...view, [category]: next };
        void viewApi.set(updated.assignees, updated.tags, updated.projects);   // writes -> syncs back
    }

    private clear() {
        void viewApi.set([], [], []);
    }

    override render() {
        const view = myView();
        const active = filtersActive(view);
        return (
            <div class={active ? "filter-bar active" : "filter-bar"}>
                <span class="filter-label">🔎 filter</span>

                <div class="filter-group">
                    <span class="filter-group-label">who</span>
                    {members().map((member) => (
                        <button class={view.assignees.includes(member.id) ? "filter-chip on" : "filter-chip"}
                                onClick={() => this.toggle("assignees", member.id)}>
                            <span class="assignee-circle small"
                                  style={`background-color:${member.color}; color:${contrastInk(member.color)}`}>
                                {firstInitial(member.username)}
                            </span>
                            {member.username}
                        </button>))}
                    <button class={view.assignees.includes(UNASSIGNED) ? "filter-chip on" : "filter-chip"}
                            title="tasks with no assignee"
                            onClick={() => this.toggle("assignees", UNASSIGNED)}>
                        <span class="assignee-circle small unassigned">∅</span>
                        unassigned
                    </button>
                </div>

                <div class="filter-group">
                    <span class="filter-group-label">tags</span>
                    {tagsList().map((tag) => (
                        <button class={view.tags.includes(tag.id) ? "filter-chip on" : "filter-chip"}
                                style={view.tags.includes(tag.id) ? `background-color:${tag.color}; color:${contrastInk(tag.color)}` : ""}
                                onClick={() => this.toggle("tags", tag.id)}>{tag.name}</button>))}
                </div>

                <div class="filter-group">
                    <span class="filter-group-label">project</span>
                    {projects().map((project) => (
                        <button class={view.projects.includes(project.code) ? "filter-chip on" : "filter-chip"}
                                onClick={() => this.toggle("projects", project.code)}>{project.code}</button>))}
                </div>

                {active ? <button class="crayon-btn filter-clear" onClick={() => this.clear()}>clear</button> : null}
            </div>
        );
    }
}
