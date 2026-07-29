// The client entrypoint: open the shared socket, wire the synced DB frame (its subscription flows
// once the socket opens), then mount the app. Pure client-side render — no SSR.

import Nano, { Component, h } from "nano-jsx";
import { sharedSocket } from "./ws/socket";
import { subscribeSharedFrames } from "./frames/shared_frames";
import { installDragController } from "./drag_controller";
import { Topbar } from "./components/Topbar";
import { Board } from "./components/Board";
import { Popups } from "./components/Popups";
import "./styles.scss";

class App extends Component {
    override render() {
        return (
            <div class="app">
                <Topbar />
                <Board />
                <Popups />
            </div>
        );
    }
}

sharedSocket.connect();
subscribeSharedFrames();
installDragController();
Nano.render(<App />, document.getElementById("root"));
