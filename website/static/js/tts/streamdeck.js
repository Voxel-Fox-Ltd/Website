/**
 * Connect to the local TTS server in order to send/receive Streamdeck events.
 * */


class StreamdeckSocket {
    constructor(username) {
        this.socket = null;
        this.username = username;
        this.interval = null;
        this.lastData = {};
    }

    async connect() {
        if(this.socket === null) {
            try {
                this.socket = new WebSocket(`wss://voxelfox.co.uk/tts-streamdeck?username=${this.username}&role=tts`);
            }
            catch(e) {
                console.error("Failed to connect to Streamdeck Websocket:", e);
                this.socket = null;
                return;
            }
            this.socket.onopen = () => {
                console.log("Connected to Streamdeck Websocket.");
            }
            this.socket.onclose = () => {
                console.log("Disconnected from Streamdeck Websocket.");
                this.socket = null;
            }
            this.socket.onmessage = (event) => {
                let data;
                try {
                    data = JSON.parse(event.data);
                }
                catch(e) {
                    console.error("Failed to parse Streamdeck Websocket message:", e);
                    return;
                }
                if(data.action = "STOP_TTS") {
                    let payload = data.payload || 0;
                    let audio = document.querySelector(`audio.tts[data-order="${payload}"]`);
                    if(audio) audio.pause();
                }
            }
            this.interval = setInterval(() => this.loop(), 10);
        }
    }

    /**
     * Grab every audio element with the "tts" class, get its "data-username" attribute, and send
     * all of those as a payload to the websocket every 1_000ms.
     * */
    loop() {
        if(this.socket !== null) {
            let payload = {};
            for(let audio of document.querySelectorAll(`audio.tts`)) {
                if(audio.paused || audio.ended || audio.url == "") continue;
                let username = audio.getAttribute("data-username");
                if(username) payload[audio.getAttribute("data-order")] = audio.getAttribute("data-username");
            }
            if(JSON.stringify(payload) == JSON.stringify(this.lastData)) return;
            this.lastData = payload;
            this.socket.send(JSON.stringify({
                "action": "UPDATE_TTS",
                "payload": payload
            }));
        }

    }

    close() {
        if(this.socket !== null) {
            this.socket.close();
            this.socket = null;
        }
        if(this.interval !== null)  {
            clearInterval(this.interval);
        }
    }
}
