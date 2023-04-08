const TWITCH_MESSAGE_REGEX = /(?:@(?<tags>.+?) )?:(?<username>.+?)!.+?@.+?\.tmi\.twitch\.tv PRIVMSG #(?<channel>.+?) :(?<message>.+)/;


class TwitchMessage {
    constructor(message) {
        let matches = TWITCH_MESSAGE_REGEX.exec(message).groups;
        this.tags = matches.tags;
        this.username = matches.username;
        this.channel = matches.channel;
        this.message = matches.message;
    }
}


const TWITCH_IRC_URI = "wss://irc-ws.chat.twitch.tv:443";


class TwitchIRC {
    constructor(accessToken, name, channels) {
        this.token = accessToken;
        this.name = name;
        this.channels = channels;
        this.socket = null;
        this.socketHavingFun = false;
    }

    /**
     * Connect to the Twitch IRC.
     * */
    async connect() {
        // Make sure we're not already connected
        if(this.socket !== null) {
            log.error("There is already a connected websocket.");
            return;
        }

        // Create a new socket instance
        this.socketHavingFun = false;
        let socket = new WebSocket(TWITCH_IRC_URI);
        this.socket = socket;
        socket.addEventListener("close", this.close.bind(this));
        socket.addEventListener("error", this.close.bind(this));
        socket.addEventListener("message", this.onMessage.bind(this));
        socket.addEventListener("open", this.onSocketOpen.bind(this));
    }

    /**
     * Close the websocket connection.
     * */
    async close() {
        if(this.socket === null) return;
        try {
            this.socket.close();
        }
        catch (e) {
        }
        this.socket = null;
        this.socketHavingFun = true;
    }

    /**
     * Add a channel to the socket listening list.
     * @param channel The channel instsance that you want to connect to.
     * */
    async addChannel(channel) {
        this.channels.push(channel);
        if(this.socket === null) return;
        await this.connectToChannel(channel);
    }

    /**
     * Handle raw messages from the Twitch IRC channel
     * @param event The message event that was received.
     * */
    async onMessage(event) {
        let data = event.data;
        // console.debug(`Received message from IRC: ${data}`);

        // Parse specific lines
        for(let lineRaw of data.split("\n")) {
            let line = lineRaw.trim();
            if(line.length === 0) continue;
            console.debug(`IRC line: ${line}`);
            if(line == ":tmi.twitch.tv NOTICE * :Login unsuccessful") {
                console.log("Failed to login to IRC");
                await this.close();
                return;
            }
            else if(line.endsWith(":Welcome, GLHF!")) {
                console.log("Logged into IRC!");
                this.socketHavingFun = true;
                return;
            }
            else if (line.startsWith(":tmi.twitch.tv ")) {
                return;
            }
            else if(line.startsWith("PING ")) {
                let toPong = line.split(" ");
                toPong.shift();
                toPong = toPong.join(" ");
                this.socket.send(`PONG ${toPong}`);
                return;
            }
            try {
                let message = new TwitchMessage(line);
                this.onTextMessage.bind(this)(message);
            }
            catch (error) {
                continue;
            }
        }
    }

    /**
     * Handle sending authentication and connecting to available channels
     * on the websocket's opening.
     * Should not be called manually.
     * */
    async onSocketOpen(sendHello = true, loop = 0) {
        // Send auth
        if(sendHello) {
            this.socket.send(`PASS oauth:${this.token}`);
            this.socket.send(`NICK ${this.name.toLowerCase()}`);
        }
        if(loop >= 5) {
            console.log("Failed to connect to IRC after 5 loops.");
            this.close();
            return;
        }

        // Wait until we're told to have fun
        if(!this.socketHavingFun) {
            setTimeout(this.onSocketOpen.bind(this), 200, false, loop + 1);
            return;
        }
        console.log("Sending cap request");
        this.socket.send(`CAP REQ :twitch.tv/tags`);

        // Connect to channels
        for(let c of this.channels) {
            await this.connectToChannel(c);
        }
    }

    /**
     * Connect to a channel. Can only be run if the websocket is currently
     * connected - inputs are silently discarded if not.
     * @param channel The channel that you want to connect to.
     * */
    async connectToChannel(channel) {
        if(this.socket === null) return;
        this.socket.send(`JOIN #${channel.toLowerCase()}`);
    }

    async onTextMessage(message) {
        console.log(`${message.username} said ${message.message}`);
        sayMessage(message);
    }
}


function getVoices() {
    return (
        speechSynthesis
        .getVoices()
        .filter((voice) => {return voice.lang.includes("en")})
    );
}


async function sayMessage(twitchMessage) {
    let voiceIndex = (
        twitchMessage
        .username
        .toLowerCase()
        .split("")
        .reduce((idx, char) => {
            return (char.charCodeAt(0) + idx) % VOICES.length;
        }, 0)
    );
    let voice = getVoices()[voiceIndex];
    let msg = new SpeechSynthesisUtterance();
    msg.text = twitchMessage.message;
    msg.voice = voice;
    window.speechSynthesis.speak(msg);
}


function loadInputs() {
    let params = new URLSearchParams(location.hash.slice(1));
    let givenToken = params.get("access_token");
    let savedToken = localStorage.getItem(`twitchAccessToken`);
    let accessToken = givenToken || savedToken;
    document.querySelector(`[name="at"]`).value = accessToken;
    document.querySelector(`[name="channel"]`).value = localStorage.getItem(`channelName`);
    document.querySelector(`[name="connect"]`).value = localStorage.getItem(`ttsChannels`);
}


function saveInputs() {
    localStorage.setItem(`twitchAccessToken`, document.querySelector(`[name="at"]`).value);
    localStorage.setItem(`channelName`, document.querySelector(`[name="channel"]`).value);
    localStorage.setItem(`ttsChannels`, document.querySelector(`[name="connect"]`).value);
}


function connectTTS() {
    saveInputs();
    let accessToken = document.querySelector(`[name="at"]`).value.trim();
    let channelName = document.querySelector(`[name="channel"]`).value.trim();
    let connectChannels = document.querySelector(`[name="connect"]`).value.trim().split("\n");
    const irc = new TwitchIRC(accessToken, channelName, connectChannels);
    document.querySelector(`#tts-connect`).disabled = true;
    irc.connect();
}


function redirectToLogin() {
    let params = {
        "client_id": "eatw6619xc67g5udj97dmx096vyxb7",
        "redirect_uri": "https://voxelfox.co.uk/static/html/twitchtts.html",
        "response_type": "token",
        "scope": "openid chat:read",
    }
    let usp = new URLSearchParams(params);
    window.location.href = (
        `https://id.twitch.tv/oauth2/authorize?`
        + usp.toString()
    );
}


function main() {
    loadInputs();
    saveInputs();
    let params = new URLSearchParams(location.search);
    if(params.get("connect") !== null) {
        if(document.querySelector(`[name="at"]`).value) {
            connectTTS();
        }
        else {
            alert("Cannot autoconnect without access token.");
        }
    }
}
main();


// const LOGDOM = document.querySelector("#log");
// function writeToLog(text) {
//     LOGDOM.value += text + "\n";
// }
// console.log = writeToLog
// console.error = writeToLog
// console.debug = writeToLog
