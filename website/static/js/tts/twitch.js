/**
 * Functions and classes relating to the Twitch IRC connection.
 * */


const TWITCH_MESSAGE_REGEX = /(?:@(?<tags>.+?) )?:(?<username>.+?)!.+?@.+?\.tmi\.twitch\.tv PRIVMSG #(?<channel>.+?) :(?<message>.+)/;


class TwitchMessage {
    constructor(message) {
        let matches = TWITCH_MESSAGE_REGEX.exec(message).groups;
        let unsplitTags = matches.tags.split(";");
        this.tags = {}
        for(let i of unsplitTags) {
            let k = i.split("=")[0];
            let v = i.split("=")[1];
            this.tags[k] = v;
        }
        this.username = matches.username;
        this.channel = matches.channel;
        this.message = matches.message;
    }

    get filteredMessage() {

        // Filter emote only messages
        if(this.tags["emote-only"]) return "";
        let workingMessage = this.message;

        // Filter commands
        if(workingMessage.startsWith("!")) return "";

        // Remove emotes from message
        let toRemoveSlices = []; // list[list[int, int]]
        let emoteLocations = this.tags["emotes"]
        if(emoteLocations) {
            let emotesIncluded = emoteLocations.split("/");
            for(let emoteInfo of emotesIncluded) {
                let emoteLocations = emoteInfo.split(":")[1].split(",");
                for(let emoteLocation of emoteLocations) {
                    toRemoveSlices.push([
                        parseInt(emoteLocation.split("-")[0]),
                        parseInt(emoteLocation.split("-")[1])
                    ])
                }
            }
        }
        toRemoveSlices.sort();
        while(toRemoveSlices.length > 0) {
            let currentSlice = toRemoveSlices.pop();
            workingMessage = (
                workingMessage.slice(0, currentSlice[0])
                + workingMessage.slice(currentSlice[1] + 1)
            )
        }

        // Remove certain words/slices
        let textSplit = workingMessage.split(" ");
        let newTextSplit = [];
        for(let i of textSplit) {

            // Filter URLs
            try {
                new URL(i);
                continue;
            }
            catch (e) {
            }

            // Filter words that are too long
            if(i.length >= 15) {
                continue;
            }

            // We good
            newTextSplit.push(i);
        }
        workingMessage = newTextSplit.join(" ");

        // Perform relevant word replacements
        for(let [k, v] of REGEX_REPLACEMENTS) {
            workingMessage = workingMessage.replace(new RegExp(k, "i"), v);
        }
        for(let [k, v] of WORD_REPLACEMENTS) {
            workingMessage = workingMessage.replace(
                new RegExp(WB + k + WB, "i"),
                (match, g1, g2) => {
                    return g1 + v + g2;
                }
            );
        }

        // And done
        return workingMessage;
    }
}


const TWITCH_IRC_URI = "wss://irc-ws.chat.twitch.tv:443";


class TwitchIRC {
    constructor(accessToken, channels) {
        this.token = accessToken;
        this.name = null;
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

        // Work out who the access token belongs to
        let site = await fetch(
            "https://id.twitch.tv/oauth2/userinfo",
            {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.token}`,
                },
            },
        );
        let data = await site.json();
        this.name = data["preferred_username"];

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
        console.log(`${message.username} said ${message.message} (${message.filteredMessage})`);
        sayMessageSE(message)  // from tts.js
    }
}
