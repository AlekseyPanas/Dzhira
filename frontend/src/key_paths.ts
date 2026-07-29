// The shared key-path grammar + tree navigation — the frontend mirror of backend/derived/key_paths.py.
// "/" separates dict keys, "[i]" suffixes address list elements, "" = whole tree. The separator MUST
// be "/" — file names like "ENG-222.json" are ordinary dict keys, so dots are data.
// (Trimmed from eventCamera's key_paths.ts: Dzhira mirrors a plain dict, so no decorated-node walkers.)

export const DELETED = "__DELETED__";

export type TPathStep = string | number;
export type TTreeValue = any;   // arbitrary mirrored json — honestly `any` (matches the Python side)

export function splitKeyPath(keyPath: string): TPathStep[] {
    if (keyPath === "") return [];
    const steps: TPathStep[] = [];
    for (const segment of keyPath.split("/")) {
        const bracketAt = segment.indexOf("[");
        steps.push(bracketAt === -1 ? segment : segment.slice(0, bracketAt));
        if (bracketAt !== -1) {
            for (const match of segment.slice(bracketAt).matchAll(/\[(\d+)\]/g)) {
                steps.push(parseInt(match[1]!, 10));
            }
        }
    }
    return steps;
}

export function joinKeyPath(parentPath: string, step: TPathStep): string {
    if (typeof step === "number") return `${parentPath}[${step}]`;
    return parentPath ? `${parentPath}/${step}` : step;
}

export function pathsIntersect(keyPathA: string, keyPathB: string): boolean {
    // One path's steps are a prefix of the other's (ancestor/descendant/equal); "" hits everything.
    const stepsA = splitKeyPath(keyPathA);
    const stepsB = splitKeyPath(keyPathB);
    const [shorter, longer] = stepsA.length <= stepsB.length ? [stepsA, stepsB] : [stepsB, stepsA];
    return shorter.every((step, index) => longer[index] === step);
}

/** True iff `keyPath` is equal to or a descendant of `rootPath`. */
export function isAtOrBelow(keyPath: string, rootPath: string): boolean {
    const rootSteps = splitKeyPath(rootPath);
    const pathSteps = splitKeyPath(keyPath);
    return rootSteps.length <= pathSteps.length
        && rootSteps.every((step, index) => pathSteps[index] === step);
}

/** Strip `rootPath` off the front of `keyPath` (which must be at-or-below it). */
export function relativeKeyPath(keyPath: string, rootPath: string): string {
    const relativeSteps = splitKeyPath(keyPath).slice(splitKeyPath(rootPath).length);
    return relativeSteps.reduce<string>((path, step) => joinKeyPath(path, step), "");
}

export function getAtPath(tree: TTreeValue, steps: TPathStep[]): { found: boolean; value: TTreeValue } {
    let current = tree;
    for (const step of steps) {
        if (typeof step === "number") {
            if (Array.isArray(current) && step >= 0 && step < current.length) {
                current = current[step];
                continue;
            }
        } else if (current !== null && typeof current === "object" && !Array.isArray(current)
                   && step in current) {
            current = current[step];
            continue;
        }
        return { found: false, value: undefined };
    }
    return { found: true, value: current };
}

/** Set with defensive parent creation (creates-are-updates; lists extend with null filler).
 *  `steps` must be non-empty. */
export function setAtPath(tree: TTreeValue, steps: TPathStep[], value: TTreeValue): void {
    let parent = tree;
    for (let stepNumber = 0; stepNumber < steps.length - 1; stepNumber++) {
        const step = steps[stepNumber]!;
        const wantedChildIsList = typeof steps[stepNumber + 1] === "number";
        const child = parent[step];
        const childHasWrongShape = wantedChildIsList ? !Array.isArray(child)
            : (child === null || typeof child !== "object" || Array.isArray(child));
        if (typeof step === "number") {
            while (parent.length <= step) parent.push(null);
            if (childHasWrongShape) parent[step] = wantedChildIsList ? [] : {};
            parent = parent[step];
        } else {
            if (childHasWrongShape) parent[step] = wantedChildIsList ? [] : {};
            parent = parent[step];
        }
    }
    const lastStep = steps[steps.length - 1]!;
    if (typeof lastStep === "number") {
        while (parent.length <= lastStep) parent.push(null);
        parent[lastStep] = value;
    } else {
        parent[lastStep] = value;
    }
}

/** Delete; a list-index delete REMOVES the element (the list shrinks — mirrors the backend rule). */
export function deleteAtPath(tree: TTreeValue, steps: TPathStep[]): boolean {
    if (steps.length === 0) return false;
    const { found, value: parent } = getAtPath(tree, steps.slice(0, -1));
    if (!found) return false;
    const lastStep = steps[steps.length - 1]!;
    if (typeof lastStep === "number") {
        if (Array.isArray(parent) && lastStep >= 0 && lastStep < parent.length) {
            parent.splice(lastStep, 1);
            return true;
        }
        return false;
    }
    if (parent !== null && typeof parent === "object" && lastStep in parent) {
        delete parent[lastStep];
        return true;
    }
    return false;
}
