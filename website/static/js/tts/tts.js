/**
 * TTS models and functions
 * */

// Regex for a word boundary
const WB = `(^|$|\\s|\\.|!|\\?|,)`;

// Playback rate min and max
var RATE_MIN = 0.07;  // 0.2;
var RATE_MAX = 10.0;  // 5.0;

// Patterns that are replaced via regex
var REGEX_REPLACEMENTS = [
    ["^[\\? ]+$", "huh?"],
    ["^[\\! ]+$", "woah"],
    ["^\\.\\.\\.$", "umm"],
    ["^LL$", "Krill issue."],
    ["(?:^|\\W)>:D(?:$|\\W)", "evil face"],
    ["(?:^|\\W)>[:=]\\((?:$|\\W)", "angry face"],
    ["(?:^|\\W)[:=]\\((?:$|\\W)", "sad face"],
    // ["(?:^|\\W)(\\d+)/10(?:$|\\W)", "\\1 out of 10"],
    ["(?:^|\\W)\\^_\\^(?:$|\\W)", "oo woo"],
    ["(?:^|\\W)[:;]3+c?", "oo woo"],
    ["bruh+", "bruh"],
    ["XD+", "XD"],
    ["u(?:wu)+", "uwu"],
    ["^\\^+$", "Yeah, agreed!"],
    ["^</3$", ""],
    // ["kae", "Kay"],
    [/(^|[\W\s])(kae)($|[\W\s])/, "$1Kay$3"],
]

// Patterns that are replaced word-for-word
var WORD_REPLACEMENTS = [
    ["twat", "twaaat"],
    ["cmon", "come on"],
    ["epicer", "epic er"],
    ["yk", "you know"],
    ["omg", "oh my god"],
    ["btw", "by the way"],
    // ["b)", "cool face"],
    ["ppl", "people"],
    ["ic", "I see"],
    [";-;", "crying"],
    ["im", "I'm"],
    ["em", "them"],
    ["ehe", "hehe"],
    ["theres", "there's"],
    ["oml", "oh my lord"],
    ["ur", "your"],
    ["idk", "I don't know"],
    ["idc", "I don't care"],
    ["ngl", "not gonna lie"],
    ["imo", "in my opinion"],
    ["imho", "in my honest opinion"],
    ["ty", "thank you"],
    ["wdym", "what do you mean"],
    ["tho", "though"],
    ["welp", "whelp"],
    ["wth", "what the hell"],
    ["wtf", "what the frick"],
    ["og", "OG"],
    ["yt", "YouTube"],
    ["jk", "JK"],
    ["afk", "AFK"],
    ["smh", "shaking my head"],
    ["gtg", "gotta go"],
    ["g2g", "gotta go"],
    ["ik", "I know"],
    ["ew", "eww"],
    ["uwu", "oo woo"],
    [":3", "oo woo"],
    [":D", "yay!"],
    ["<3", "heart"],
    ["fr", "for real"],
    ["frfr", "for real for real"],
    ["ikr", "I know, right?"],
    ["yw", "you're welcome"],
    ["dont", "don't"],
    ["rn", "right now"],
    ["ig", "I guess"],
    ["alr", "alright"],
    ["nvm", "nevermind"],
    ["sus", "suss"],
    ["gn", "goodnight"],
    ["vtuber", "vee toober"],
    ["envtuber", "E N vee toober"],
    ["pls", "please"],
    ["tysm", "thank you so much"],
    ["ily", "I love you"],
    ["thx", "thanks"],
    ["abt", "about"],
    ["plz", "please"],
    ["rlly", "really"],
    ["wont", "won't"],
    ["data", "dayta"],
    ["grr", "gyrrr"],
    ["tf", "the frick"],
    ["tbh", "to be honest"],
    ["brb", "be right back"],
    ["hru", "how are you"],
    ["irl", "IRL"],
    ["bf", "boy-frog"],
    ["wyd", "what you doing"],
    ["bbg", "babygirl"],
    ["stfu", "shut the heck up"],
    ["omfg", "oh my hecking god"],
    ["wingman", "wing-man"],
    ["havent", "haven't"],
    ["hmpf", "hmpf"],
    ["kys", "reconsider what you are doing"],
    ["/th", "slash threat"],
    ["nfts", "NFTs"],
    ["nft", "NFT"],
    ["ai", "AI"],
    ["rq", "real quick"],
    ["m8", "mate"],
    ["wb", "wub"],
    ["tn", "tonight"],
    ["henlowo", "hen-low-woah"],
    ["hellowo", "hell-oh-woah"],
    ["nyah", "nia"],
    ["fml", "frick my life"],
    ["tos", "toss"],
    ["ttyl", "talk to you later"],
    ["it", "it"],
    ["tts", "text to speech"],
    ["bo'om", "boddum"],
    ["lol", "teehee"],
    ["lmao", "teehee"],
    ["lmafo", "teehee"],
    ["lmfao", "teehee"],
    ["google", "gog-lay"],
    ["smth", "something"],
    ["ily2", "i love you too"],
    ["wha", "waa"],
    // ["chatgpt", "chat GPT"],
    ["chatgpt", "chatgăpît"],
    ["istg", "I swear to God"],
    ["LFG", "let's fucking go"],
]


// Users that get ignored by TTS
var IGNORED_USERS = [
    "cloudbot",
    "streamlabs",
    "streamelements",
];


/**
 * A voice instance that can be used via StreamElements' API
 * */
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
    // en-US
    new Voice("Danielle"),
    new Voice("Gregory"),
    new Voice("Ivy"),
    new Voice("Joanna"),
    new Voice("Joey"),
    new Voice("Justin"),
    new Voice("Kendra"),
    new Voice("Kevin"),
    new Voice("Kimberly"),
    new Voice("Matthew"),
    new Voice("Ruth"),
    new Voice("Salli"),
    new Voice("Stephen"),

    // en-GB
    new Voice("Amy"),
    new Voice("Arthur"),
    new Voice("Brian"),
    new Voice("Emma"),

    // en-AU
    new Voice("Olivia"),

    // en-IN
    new Voice("Kajal"),

    // en-IE
    new Voice("Niamh"),

    // en-NZ
    new Voice("Aria"),

    // en-SG
    new Voice("Jasmine"),

    // en-ZA
    new Voice("Ayanda"),

    // es
    new Voice("Lucia", "es"),  // es-ES
    new Voice("Sergio", "es"),  // es-ES
    new Voice("Mia", "es"),  // es-MX
    new Voice("Andrés", "es"),  // es-MX
    new Voice("Lupe", "es"),  // es-US
    new Voice("Pedro", "es"),   // es-US
];



/**
 * Queue a message into the TTS
 * */
async function sayMessage(twitchMessage) {

    // Filter by username
    if(IGNORED_USERS.includes(twitchMessage.username.toLowerCase())) return;

    // Make sure we have something to say
    if(!twitchMessage.filteredMessage) return;

    // Get a voice
    let voice = undefined;
    let voiceOverride = "";
    for(let v of document.querySelectorAll("#voice-table tbody tr")) {
        if(v.querySelector(".username").value.toLowerCase() != twitchMessage.username.toLowerCase()) continue;
        voiceOverride = v.querySelector(".voices").value;
        if(voiceOverride == "") return;
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
        voice = VOICES.filter(x => x.name == voiceOverride)[0];
    }
    if(voice === undefined) voice = VOICES[0];

    // Get TTS URL
    let text = twitchMessage.filteredMessage;
    let rate = 1;
    let match = /^(-?\d+|-?(?:\d+\.\d+))\|(.*)$/g.exec(text);
    if(match) {
        text = match[2];
        rate = Math.max(RATE_MIN, Math.min(parseFloat(match[1]), RATE_MAX));
    }
    let audioData;
    try {
        audioData = await pollySynthTTS(text, voice.name);
    }
    catch(e) {
        console.error("TTS synthesis error:", e);
        return;
    }

    // Add to queue
    queueAudio(audioData, rate, twitchMessage.username.toLowerCase())
}


function getAudioEnded(audio) {
    return audio.ended || audio.src == "" || audio.paused || (audio.error && audio.error.code == 4)
}


function getNonPlayingAudioFromArray(audioArray) {
    let validAudio = [];
    for(node of audioArray) {
        if(getAudioEnded(node)) {
            validAudio.push(node);
        }
    }
    return validAudio;
}


function getPlayingAudioFromArray(audioArray) {
    let validAudio = [];
    for(node of audioArray) {
        if(!getAudioEnded(node)) {
            validAudio.push(node);
        }
    }
    return validAudio;
}


function getAvailableTTSNodes(username=null) {
    let audio = [];
    switch(document.querySelector("input[name='output-type']:checked").value) {
        case "all-queued":
            audio = document.querySelectorAll("audio.tts[data-first]");
            break;
        case "by-user":
            let temp = document.querySelectorAll(`audio.tts[data-username="${username}"]`);
            let temp2 = getPlayingAudioFromArray(temp);
            if(temp2.length > 0) return [];
        case "simultaneous":
        default:
            audio = document.querySelectorAll("audio.tts");
            break;
    }
    let validAudio = getNonPlayingAudioFromArray(audio);
    return validAudio;
}


var audioQueue = [];
function queueAudio(audioData, rate=1, username=null) {
    audioQueue.push([audioData, rate, username]);
    let audio = getAvailableTTSNodes();
    if(audio) playNextTTSTrack();
}
function playNextTTSTrack() {
    if(audioQueue.length == 0) return;  // no queued audio - do nothing
    let audio = getAvailableTTSNodes(audioQueue[0][2]);  // get available audio nodes for that user
    if(audio.length == 0) return;  // no available audio nodes - do nothing
    let [audioData, rate, username] = audioQueue.shift();  // get the next audio from the queue and play it
    let blob = new Blob([audioData], { type: "audio/mpeg" });
    let blobUrl = URL.createObjectURL(blob);
    audio[0].dataset.username = username;
    audio[0].src = blobUrl;
    audio[0].playbackRate = rate;
    audio[0].play();
}
document.querySelectorAll("audio.tts").forEach(a => a.addEventListener("ended", playNextTTSTrack));
document.querySelectorAll("audio.tts").forEach(a => a.addEventListener("pause", playNextTTSTrack));
