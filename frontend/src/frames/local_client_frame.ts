// LocalClientFrame: frontend-owned shared state (which popout is open, the in-flight editor draft,
// the live drag state). Everyone reads/subscribes; writers just call write/deleteKey.
// (Ported from eventCamera's local_client_frame.ts.)

import { AClientFrame } from "./a_client_frame";
import { DELETED, deleteAtPath, setAtPath, splitKeyPath, type TTreeValue } from "../key_paths";

export class LocalClientFrame extends AClientFrame {

    constructor(initialState: TTreeValue) {
        super(initialState);
    }

    /** Mutate + notify subscribers of exactly what changed. */
    write(keyPath: string, value: TTreeValue): void {
        if (keyPath === "") {
            this.swapState(value);
        } else {
            const state = this.currentState();
            setAtPath(state, splitKeyPath(keyPath), value);
            this.swapState(state);                          // same object; Store notifies anyway
        }
        this.fireChange(keyPath, value);
    }

    deleteKey(keyPath: string): void {
        const state = this.currentState();
        if (deleteAtPath(state, splitKeyPath(keyPath))) {
            this.swapState(state);
            this.fireChange(keyPath, DELETED);
        }
    }
}
