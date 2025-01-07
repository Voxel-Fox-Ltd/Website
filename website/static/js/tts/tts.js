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
    ["(?:^|\\W):3+c?", "oo woo"],
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


// A list of all available voices
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


/**
 * Queue a message into the TTS
 * */
async function sayMessageSE(twitchMessage) {

    // Filter by username
    if(IGNORED_USERS.includes(twitchMessage.username.toLowerCase())) return;

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
    let usp = new URLSearchParams({
        "voice": voice.name,
        "text": text,
    });
    let voiceUrl = (
        "https://api.streamelements.com/kappa/v2/speech?"
        + usp.toString()
    );

    // Add to queue
    queueAudio(voiceUrl, rate)
}


function getAvailableTTSNodes() {
    let audio = document.querySelectorAll("audio.tts");
    let validAudio = [];
    for(node of audio) {
        if(node.ended || node.src == "" || node.paused || (node.error && node.error.code == 4)) {
            validAudio.push(node);
        }
    }
    return validAudio;
}


var audioQueue = [];
function queueAudio(url, rate=1) {
    audioQueue.push([url, rate]);
    let audio = getAvailableTTSNodes();
    if(audio) playNextTTSTrack();
}
function playNextTTSTrack() {
    let audio = getAvailableTTSNodes();
    if(audioQueue.length > 0) {
        let [url, rate] = audioQueue.shift();
        audio[0].src = url;
        audio[0].playbackRate = rate;
        audio[0].play();
    }
}
document.querySelectorAll("audio.tts").forEach(a => a.addEventListener("ended", playNextTTSTrack));
document.querySelectorAll("audio.tts").forEach(a => a.addEventListener("pause", playNextTTSTrack));
