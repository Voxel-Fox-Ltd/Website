/**
 * Connect to the local TTS server in order to send/receive Streamdeck events.
 * */


class StreamdeckSocket {
    constructor(username) {
        this.socket = null;
        this.username = username;
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
                let data = JSON.parse(event.data);
                if(data.action = "STOP_TTS") {
                    payload = data.payload || 0;
                    let audio = document.querySelector(`audio.tts[data-order=${payload}]`);
                    if(audio) audio.pause();
                }
            }
        }
    }

    close() {
        if(this.socket !== null) {
            this.socket.close();
            this.socket = null;
        }
    }
}
