/**
 * Functions and classes relating to the Twitch IRC connection.
 * */


const TWITCH_MESSAGE_REGEX = /(?:@(?<tags>.+?) )?:(?<username>.+?)!.+?@.+?\.tmi\.twitch\.tv PRIVMSG #(?<channel>.+?) :(?<message>.+)/;
const MAX_WORD_LENGTH = 50;


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

        // Filter by user type where applicable (eg mod/sub/vip/etc)
        let userTypeFlags = 0;
        for(let i of document.querySelectorAll(".output-user-type-checkbox")) {
            if(i.checked) {
                userTypeFlags |= parseInt(i.value);
            }
        }
        let shouldContinue = false;
        if(userTypeFlags && 1) {
            shouldContinue = true;
        }
        if(userTypeFlags && 4) {
            if(this.tags["subscriber"] == "1") shouldContinue = true;
        }
        if(userTypeFlags && 8) {
            if(this.tags["vip"] == "1") shouldContinue = true;
        }
        if(userTypeFlags && 16) {
            if(this.tags["mod"] == "1") shouldContinue = true;
        }
        if(!shouldContinue) return "";

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
                let possibleUrl = new URL(i);
                if(possibleUrl.host.toLowerCase() == "http" || possibleUrl.host.toLowerCase() == "https") {
                    continue;
                }
            }
            catch (e) {
            }

            // Filter words that are too long
            if(i.length >= MAX_WORD_LENGTH) {
                continue;
            }

            // We good
            newTextSplit.push(i);
        }
        workingMessage = newTextSplit.join(" ");

        // Perform relevant word replacements
        // Do this until no matches are found
        let anyMatch = false;
        // while(true) {
        for(let [k, v] of REGEX_REPLACEMENTS) {
            let match = new RegExp(k, "i").exec(workingMessage);
            if(match) {
                anyMatch = true;
                workingMessage = workingMessage.replace(new RegExp(k, "i"), v);
            }
        }
        for(let [k, v] of WORD_REPLACEMENTS) {
            workingMessage = workingMessage.replace(
                new RegExp(WB + k + WB, "i"),
                (match, g1, g2) => {
                    return g1 + v + g2;
                }
            );
        }
        //     if(!anyMatch) break;
        // }

        // And done
        return workingMessage;
    }
}


const TWITCH_IRC_URI = "wss://irc-ws.chat.twitch.tv:443";


class TwitchIRC {

    constructor(accessToken, channels) {
        this.token = accessToken;
        this.name = null;
        this.userId = null;
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
        if(!site.ok) {
            return;
        }

        let data = await site.json();
        this.name = data["preferred_username"];
        this.userId = data["sub"];

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
            else if(line.startsWith(":tmi.twitch.tv ")) {
                return;
            }
            else if(line.startsWith("PING ")) {
                let toPong = line.split(" ");
                toPong.shift();
                toPong = toPong.join(" ");
                this.socket.send(`PONG ${toPong}`);
                return;
            }
            else {
                try {
                    let message = new TwitchMessage(line);
                    await this.onTextMessage.bind(this)(message);
                }
                catch (error) {
                    console.error("Failed to parse Twitch IRC message:", error);
                    continue;
                }
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
        await sayMessage(message)  // from tts.js
    }
}


class PointsReward {

    constructor(data) {
        this.id = data.id;
        this.channelId = data["broadcaster_id"];
        this.title = data.title;
        this.prompt = data.prompt;
        this.cost = data.cost;
        this.subOnly = data["is_sub_only"];
    }

    async updateStatus(clientId, token, enabledStatus) {
        let site = await fetch(
            (
                "https://api.twitch.tv/helix"
                + "/channel_points/custom_rewards"
                + `?broadcaster_id=${this.channelId}`
                + `&id=${this.id}`
            ),
            {
                method: "PATCH",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Client-ID": clientId,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    "is_enabled": enabledStatus,
                }),
            },
        );
        if(!site.ok) return;
        let json = await site.json();
        document.querySelector(`.sound[data-id="${json.data[0].id}"] input[name="enabled"]`).checked = json.data[0]["is_enabled"];
    }

    async enable(clientId, token) {
        await this.updateStatus(clientId, token, true);
    }

    async disable(clientId, token) {
        await this.updateStatus(clientId, token, false);
    }

}


class PointsRedeem {

    constructor(data) {
        this.id = data.id;
        this.user = data.user.login;
        this.userId = data.user.id;
        this.timestamp = data["redeemed_at"];
        this.reward = new PointsReward(data.reward);
        this.reward.channelId = data["channel_id"];
        this.userInput = data["user_input"];
        this.status = data.status;
    }

    async updateStatus(clientId, token, status) {
        return await fetch(
            (
                "https://api.twitch.tv/helix"
                + "/channel_points/custom_rewards/redemptions"
                + `?broadcaster_id=${this.reward.channelId}`
                + `&reward_id=${this.reward.id}`
                + `&id=${this.id}`
            ),
            {
                method: "PATCH",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Client-ID": clientId,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    status: status,
                }),
            },
        );
    }

    async cancel(clientId, token) {
        return await this.updateStatus(clientId, token, "CANCELED");
    }

    async fulfil(clientId, token) {
        return await this.updateStatus(clientId, token, "FULFILLED");
    }
}


const TWITCH_PUBSUB_URI = "wss://pubsub-edge.twitch.tv";


class TwitchPubSub {

    constructor(accessToken, userId, clientId) {
        this.token = accessToken;
        this.userId = userId;
        this.clientId = clientId;
        this.socket = null;
    }

    async pingLoop() {
        while(true) {
            if(this.socket === null) return;
            console.log("Sending ping")
            await this.send({type: "PING"});
            await new Promise(r => setTimeout(r, 4 * 60 * 1_000));
        }
    }

    async updateRewardDom(initialSleepTime = 0) {
        if(initialSleepTime > 0) {
            await new Promise(r => setTimeout(r, initialSleepTime));
        }
        while(true) {
            if(this.socket === null) return;
            console.log("Getting updated DOM")
            let currentRewards = await fetch(
                (
                    "https://api.twitch.tv/helix/channel_points/custom_rewards"
                    + `?broadcaster_id=${this.userId}`
                    + "&only_manageable_rewards=true"
                ),
                {
                    headers: {
                        "Authorization": `Bearer ${this.token}`,
                        "Client-ID": this.clientId,
                    }
                }
            );
            let currentRewardData = await currentRewards.json();
            for(let r of currentRewardData.data) {
                let box = document.querySelectorAll(`.sound[data-id="${r.id}"] input[name="enabled"]`);
                box.checked = r["is_enabled"];
            }
            await new Promise(r => setTimeout(r, 10 * 1_000));
        }
    }

    /**
     * Connect to pubsub.
     * */
    async connect() {
        if(!document.querySelector(`input[name="sound-redeems-enabled"]`).checked) return;
        if(this.socket !== null) throw new Error("Socket is already open");
        let socket = new WebSocket(TWITCH_PUBSUB_URI);
        this.socket = socket;
        socket.addEventListener("close", this.close.bind(this));
        socket.addEventListener("error", this.close.bind(this));
        socket.addEventListener("message", this.onMessage.bind(this));
        socket.addEventListener("open", this.onSocketOpen.bind(this));
    }

    /**
     * Close the open websocket connection.
     * */
    async close() {
        if(this.socket === null) return;
        try {
            this.socket.close();
        }
        catch (e) {
        }
        this.socket = null;
    }

    /**
     * Send a message to the open websocket.
     * */
    async send(message) {
        if(this.socket === null) throw new Error("No open socket");
        await this.socket.send(JSON.stringify(message));
    }

    /**
     * Handle sending authentication and connecting to available channels
     * on the websocket's opening.
     * Should not be called manually.
     * */
    async onSocketOpen() {
        console.log("Sending listen request");
        await this.send({
            "type": "LISTEN",
            "data": {
                "topics": [`channel-points-channel-v1.${this.userId}`],
                "auth_token": this.token,
            }
        });

        console.log("Creating rewards");
        let currentRewards = await fetch(
            (
                "https://api.twitch.tv/helix/channel_points/custom_rewards"
                + `?broadcaster_id=${this.userId}`
                + "&only_manageable_rewards=true"
            ),
            {
                headers: {
                    "Authorization": `Bearer ${this.token}`,
                    "Client-ID": this.clientId,
                }
            }
        );
        let currentRewardData = await currentRewards.json();
        for(let r of currentRewardData.data) {
            if(r.title.startsWith("VFTTS Sound: ")) {
                let title = r.title.substr("VFTTS Sound: ".length);
                let reward = document.querySelector(`.sound[data-name="${title}"]`);
                reward.dataset.id = r.id;
                reward.querySelector(`input[name="enabled"]`).checked = r["is_enabled"];
            }
        }
        for(let r of document.querySelectorAll(`.sound[data-id=""]`)) {
            let createdSite = await fetch(
                (
                    "https://api.twitch.tv/helix/channel_points/custom_rewards"
                    + `?broadcaster_id=${this.userId}`
                ),
                {
                    method: "POST",
                    headers: {
                        "Authorization": `Bearer ${this.token}`,
                        "Client-ID": this.clientId,
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        title: `VFTTS Sound: ${r.dataset.name}`,
                        cost: 100,
                        is_enabled: r.querySelector(`input[name="enabled"]`).checked,
                        background_color: "#D580D0",
                    }),
                },
            );
            let data = await createdSite.json();
            r.dataset.id = data.data[0].id;
        }

        console.log("Creating reward loop");
        this.updateRewardDom(60_000)
        console.log("Creating ping loop");
        this.pingLoop();
    }

    /**
     * Receive a message from the socket.
     * */
    async onMessage(message) {
        let data = JSON.parse(event.data);
        if(data.type == "RESPONSE") {
            if(data.error) {
                console.log("Failed to connect to PubSub websocket");
                console.log(data);
                try {
                    await self.close();
                }
                catch (e) {
                }
            }
            return;
        }
        else if(data.type == "PONG") {
            console.log("Received pong");
            return;
        }
        else if(data.type == "RECONNECT") {
            console.log("Asked to reconnect");
            this.close().then(this.connect);
            return;
        }
        else if(data.type == "MESSAGE") {
            let messageData = JSON.parse(data.data.message);
            switch(data.data.topic) {
                case `channel-points-channel-v1.${this.userId}`:
                    this.onPointsRedeem(new PointsRedeem(messageData.data.redemption));
                    return;
            }
        }
        console.log("Can't work out what to do with message from Twitch.");
        console.log(data);
    }

    async onPointsRedeem(redeem) {
        if(redeem.reward.title.startsWith("VFTTS Sound: ")) {
            this.onSoundRedeem(redeem);
        }
        else {
            await redeem.cancel(this.clientId, this.token);
        }
    }

    async onSoundRedeem(redeem) {
        let allAudio = [
            ...document.querySelectorAll(`.sound[data-id="${redeem.reward.id}"] audio`)
        ];
        let playableAudio = allAudio.filter(a => a.paused);
        if(playableAudio.length == 0) {
            await redeem.cancel(this.clientId, this.token);
            return;
        }
        playableAudio[0].volume = 0.35;
        playableAudio[0].play();
        await redeem.fulfil(this.clientId, this.token);
    }
}
