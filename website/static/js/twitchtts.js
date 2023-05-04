const TWITCH_MESSAGE_REGEX = /(?:@(?<tags>.+?) )?:(?<username>.+?)!.+?@.+?\.tmi\.twitch\.tv PRIVMSG #(?<channel>.+?) :(?<message>.+)/;


const WB = `(^|$|\\s|\\.|!|\\?|,)`;
const REGEX_REPLACEMENTS = [
    ["^[\\? ]+$", "huh?"],
    ["^[\\! ]+$", "woah"],
    ["^\\.\\.\\.$", "umm"],
    ["^LL$", "Skill issue."],
    ["(?:^|\\W)>:D(?:$|\\W)", "evil face"],
    ["(?:^|\\W)>[:=]\\((?:$|\\W)", "angry face"],
    ["(?:^|\\W)[:=]\\((?:$|\\W)", "sad face"],
    ["(?:^|\\W)(\\d+)/10(?:$|\\W)", "\\1 out of 10"],
    ["(?:^|\\W)\\^_\\^(?:$|\\W)", "oo woo"],
    ["(?:^|\\W):3+c?", "oo woo"],
    ["bruh+", "bruh"],
    ["XD+", "XD"],
    ["u(?:wu)+", "uwu"],
    ["^\\^+$", "Yeah, agreed!"],
    ["^</3$", ""],
    [`kae`, "Kay"],
]
const WORD_REPLACEMENTS = [
    [`twat`, "twaaat"],
    [`cmon`, "come on"],
    [`epicer`, "epic er"],
    [`yk`, "you know"],
    [`omg`, "oh my god"],
    [`btw`, "by the way"],
    [`b\\)`, "cool face"],
    [`ppl`, "people"],
    [`ic`, "I see"],
    [`;\\-;`, "crying"],
    [`im`, "I'm"],
    [`em`, "them"],
    [`theres`, "there's"],
    [`oml`, "oh my lord"],
    [`ur`, "your"],
    [`idk`, "I don't know"],
    [`idc`, "I don't care"],
    [`ngl`, "not gonna lie"],
    [`imo`, "in my opinion"],
    [`imho`, "in my honest opinion"],
    [`ty`, "thank you"],
    [`wdym`, "what do you mean"],
    [`tho`, "though"],
    [`welp`, "whelp"],
    [`wth`, "what the hell"],
    [`wtf`, "what the frick"],
    [`og`, "OG"],
    [`yt`, "YouTube"],
    [`jk`, "JK"],
    [`afk`, "AFK"],
    [`smh`, "shaking my head"],
    [`gtg`, "gotta go"],
    [`g2g`, "gotta go"],
    [`ik`, "I know"],
    [`ew`, "eww"],
    [`uwu`, "oo woo"],
    [`:3`, "oo woo"],
    [`:D`, "yay!"],
    [`<3`, "heart"],
    [`fr`, "for real"],
    [`frfr`, "for real for real"],
    [`ikr`, "I know, right?"],
    [`yw`, "you're welcome"],
    [`dont`, "don't"],
    [`rn`, "right now"],
    [`ig`, "I guess"],
    [`alr`, "alright"],
    [`nvm`, "nevermind"],
    [`sus`, "suss"],
    [`gn`, "goodnight"],
    [`vtuber`, "vee toober"],
    [`envtuber`, "E N vee toober"],
    [`pls`, "please"],
    [`tysm`, "thank you so much"],
    [`ily`, "I love you"],
    [`thx`, "thanks"],
    [`abt`, "about"],
    [`plz`, "please"],
    [`rlly`, "really"],
    [`wont`, "won't"],
    [`data`, "dayta"],
    [`grr`, "gyrrr"],
    [`tf`, "the frick"],
    [`tbh`, "to be honest"],
    [`brb`, "be right back"],
    [`hru`, "how are you"],
    [`irl`, "IRL"],
    [`bf`, "boy-frog"],
    [`wyd`, "what you doing"],
    [`bbg`, "babygirl"],
    [`stfu`, "shut the heck up"],
    [`omfg`, "oh my hecking god"],
    [`wingman`, "wing-man"],
    [`havent`, "haven't"],
    [`hmpf`, "hmpf"],
    [`kys`, "reconsider what you are doing"],
    [`\\/th`, "slash threat"],
    [`nfts`, "NFTs"],
    [`nft`, "NFT"],
    [`ai`, "AI"],
    [`rq`, "real quick"],
    [`m8`, "mate"],
    [`wb`, "wub"],
    [`tn`, "tonight"],
    [`henlowo`, "hen-low-woah"],
    [`hellowo`, "hell-oh-woah"],
    [`nyah?`, "nia"],
    [`fml`, "frick my life"],
    [`tos`, "toss"],
    [`ttyl`, "talk to you later"],
    [`it`, "it"],
    [`tts`, "text to speech"],
    [`bo'om`, "boddum"],
    [`lol`, "teehee"],
    [`lmao`, "teehee"],
    [`lmafo`, "teehee"],
    [`lmfao`, "teehee"],
    [`google`, "gog-lay"],
    ["smth", "something"],
    ["ily2", "i love you too"],
    ["wha", "what"],
]


class Voice {
    constructor(apiName, language=null, displayName=null) {
        this.name = apiName;
        this.language = language === null ? "en" : language;
        this._displayName = displayName;
    }

    get display() {
        let builder = this._displayName === null ? this.name : this._displayName;
        if(this.language == "en") return builder;
        return `${builder} (${this.language})`;
    }
}


const VOICES = [
    new Voice("Brian"),
    new Voice("Amy"),
    new Voice("Emma"),
    new Voice("Geraint"),
    new Voice("Russell"),
    new Voice("Nicole"),
    new Voice("Joey"),
    new Voice("Justin"),
    new Voice("Matthew"),
    new Voice("Joanna"),
    new Voice("Kendra"),
    new Voice("Kimberly"),
    new Voice("Salli"),
    new Voice("Raveena"),
    new Voice("Enrique", "es"),
    new Voice("Conchita", "es"),
    new Voice("es-ES-Standard-A", "es", "Lucia"),
    new Voice("Mia", "es"),
    new Voice("Miguel", "es"),
    new Voice("Penelope", "es"),
];


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
        sayMessageSE(message)
    }
}


var filterUsers = [
    "cloudbot",
    "streamlabs"
]
async function sayMessageSE(twitchMessage) {

    // Filter by username
    if(filterUsers.includes(twitchMessage.username.toLowerCase())) return;

    // Log username
    if(!chatUsers.includes(twitchMessage.username)) {
        chatUsers.push(twitchMessage.username.toLowerCase());
        updateVoiceUsernames();
    }

    // Make sure we have something to say
    if(!twitchMessage.filteredMessage) return;

    // Get a voice
    let voice = undefined;
    let voiceOverride = "";
    for(let v of document.querySelectorAll("#voices div")) {
        if(v.querySelector(".username").value != twitchMessage.username.toLowerCase()) continue;
        voiceOverride = v.querySelector(".voices").value;
        break;
    }
    if(voiceOverride == "") {
        let englishVoices = VOICES.filter(x => x.language == "en");
        let voiceIndex = (
            twitchMessage
            .username
            .toLowerCase()
            .split("")
            .reduce((idx, char) => {
                return (char.charCodeAt(0) + idx) % englishVoices.length;
            }, 0)
        );
        voice = englishVoices[voiceIndex];
    }
    else {
        voice = voiceOverride;
    }
    if(voice === undefined) voice = "Brian";

    // Get TTS URL
    let usp = new URLSearchParams({
        "voice": voice.name,
        "text": twitchMessage.filteredMessage,
    });
    let voiceUrl = (
        "https://api.streamelements.com/kappa/v2/speech?"
        + usp.toString()
    );

    // // Create element
    // let audio = document.createElement("audio");
    // audio.autoplay = true;
    // let source = document.createElement("source");
    // source.src = voiceUrl;
    // audio.appendChild(source);

    // Add to queue
    queueAudio(voiceUrl)
}


var audioQueue = [];
function queueAudio(url) {
    let audio = document.querySelector("#voice-container audio");
    if(audio.ended || audio.src == "") {
        audio.src = url;
        audio.play();
    }
    else {
        audioQueue.push(url);
    }
}
document.querySelector("#voice-container audio").addEventListener("ended", () => {
    if(audioQueue.length > 0) {
        let url = audioQueue.shift();
        let audio = document.querySelector("#voice-container audio");
        audio.src = url;
        audio.play();
    }
});


var chatUsers = [];
function updateVoiceUsernames() {
    let voiceSelect = document.querySelector("#voices .template .voices");
    if(voiceSelect.length == 0) {
        for(let v of VOICES) {
            let voiceOption = document.createElement("option");
            voiceOption.innerText = v.display;
            voiceOption.value = v.name;
            voiceSelect.appendChild(voiceOption);
        }
    }
    let allUserSelect = document.querySelectorAll("#voices .username");
    for(let userSelect of allUserSelect) {
        for(let user of chatUsers) {
            if(userSelect.querySelector(`option[value="${user}"]`) === null) {
                let uOpt = document.createElement("option");
                uOpt.value = user;
                uOpt.innerText = user;
                userSelect.appendChild(uOpt);
            }
        }
    }
}
updateVoiceUsernames();


function addNewVoiceOverride(twitchUsername, voice) {
    if(twitchUsername !== null) {
        if(document.querySelector(`#voices .template .username option[value="${twitchUsername}"]`) === null) {
            chatUsers.push(twitchUsername);
            updateVoiceUsernames();
        }
    }
    let newVoice = document.querySelector("#voices .template").cloneNode(true);
    newVoice.classList = [];
    for(let opt of newVoice.querySelectorAll("option")) opt.selected = false;
    if(twitchUsername !== null) {
        newVoice.querySelector(`.username option[value="${twitchUsername}"]`).selected = true;
    }
    if(voice !== null) {
        newVoice.querySelector(`.voices option[value="${voice}"]`).selected = true;
    }
    document.querySelector("#voices").appendChild(newVoice);
}


function loadInputs() {
    let params = new URLSearchParams(location.hash.slice(1));
    let givenToken = params.get("access_token");
    let savedToken = localStorage.getItem(`twitchAccessToken`);
    let accessToken = givenToken || savedToken;
    document.querySelector(`[name="at"]`).value = accessToken;
    document.querySelector(`[name="connect"]`).value = localStorage.getItem(`ttsChannels`);
    let voices = JSON.parse(localStorage.getItem(`voiceOverrides`));
    let voiceDom = document.querySelector("#voices");
    for(let vdo of voiceDom.children) {
        if(!vdo.classList.contains("template")) vdo.remove();
    }
    for(let u in voices) {
        addNewVoiceOverride(u, voices[u]);
    }
}


function serializeVoiceOverrides() {
    let voices = document.querySelectorAll("#voices div");
    let selected = {};
    for(let voiceNode of voices) {
        let user = voiceNode.querySelector(".username").value;
        let voiceName = voiceNode.querySelector(".voices").value;
        if(user == "" || voiceName == "") continue;
        selected[user] = voiceName;
    }
    return JSON.stringify(selected);
}


function saveInputs() {
    localStorage.setItem(`twitchAccessToken`, document.querySelector(`[name="at"]`).value);
    localStorage.setItem(`ttsChannels`, document.querySelector(`[name="connect"]`).value);
    localStorage.setItem(`voiceOverrides`, serializeVoiceOverrides());
}


var irc = null;
function connectTTS() {
    if(irc === null) {
        saveInputs();
        document.querySelector(`[name="connect"]`).disabled = true;
        document.querySelector(`#login-button`).disabled = true;
        let accessToken = document.querySelector(`[name="at"]`).value.trim();
        let connectChannels = document.querySelector(`[name="connect"]`).value.trim().split("\n");
        irc = new TwitchIRC(accessToken, connectChannels);
        irc.connect();
    }
    else {
        irc.close();
        document.querySelector(`[name="connect"]`).disabled = false;
        document.querySelector(`#login-button`).disabled = false;
        irc = null;
    }
    document.querySelector("#tts-connect").innerHTML = (
        irc === null ? "Connect TTS" : "Disconnect TTS"
    );
}


function changeOutput() {
    navigator.mediaDevices.selectAudioOutput().then((sink) => {
        console.log(`Setting media to sink ${sink.deviceId}`);
        let devs = document.querySelectorAll("audio,video");
        for(let d of devs) {
            d.setSinkId(sink.deviceId)
            console.log(d);
        }
    }) ;
}


function redirectToLogin() {
    let params = {
        "client_id": "eatw6619xc67g5udj97dmx096vyxb7",
        "redirect_uri": "https://voxelfox.co.uk/tts",
        "response_type": "token",
        "scope": "openid chat:read",
        "claims": JSON.stringify({"userinfo": {"preferred_username": null}}),
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
