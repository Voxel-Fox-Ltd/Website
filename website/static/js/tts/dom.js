/**
 * Functions and classes relating to the page DOM
 * */

// A list of users who are in chat
var chatUsers = [];

/**
 * Update all of the username dropdowns for the page.
 * */
function updateVoiceUsernames() {

    // Get the voices from the template
    let voiceSelect = document.querySelector("#voices .template .voices");

    // Generate if none exist
    if(voiceSelect.length == 0) {
        let voiceOption = document.createElement("option");
        voiceOption.innerText = "";
        voiceOption.value = "";
        voiceSelect.appendChild(voiceOption);
        for(let v of VOICES) {
            voiceOption = document.createElement("option");
            voiceOption.innerText = v.display;
            voiceOption.value = v.name;
            voiceSelect.appendChild(voiceOption);
        }
    }

    // Populate any user dropdowns that are empty
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


/**
 * Add a new voice override node to the list.
 * */
function addNewVoiceOverride(twitchUsername, voice) {
    if(twitchUsername !== null) {
        if(document.querySelector(`#voices .template .username option[value="${twitchUsername}"]`) === null) {
            chatUsers.push(twitchUsername);
            updateVoiceUsernames();
        }
    }
    let newVoice = document.querySelector("#voices .template").cloneNode(true);
    newVoice.classList.remove("template");
    for(let opt of newVoice.querySelectorAll("option")) opt.selected = false;
    if(twitchUsername !== null) {
        newVoice.querySelector(`.username option[value="${twitchUsername}"]`).selected = true;
    }
    if(voice !== null) {
        newVoice.querySelector(`.voices option[value="${voice}"]`).selected = true;
    }
    document.querySelector("#voices").appendChild(newVoice);
}


/**
 * Serialize all of the voice override nodes into a JSON string.
 * */
function serializeVoiceOverrides() {
    let voices = document.querySelectorAll("#voices > div");
    let selected = {};
    for(let voiceNode of voices) {
        let user = voiceNode.querySelector(".username").value;
        let voiceName = voiceNode.querySelector(".voices").value;
        if(user == "" || voiceName == "") continue;
        selected[user] = voiceName;
    }
    return JSON.stringify(selected);
}


/**
 * Serialize all of the enabled points rewards into a JSON string.
 * */
function serializeSoundRedeems() {
    let sounds = document.querySelectorAll(".sound")
    let selected = {};
    for(let soundNode of sounds) {
        selected[soundNode.dataset.name] = soundNode.querySelector("[name=managed]").checked;
    }
    return JSON.stringify(selected);
}


/**
 * Load all of the inputs from localstorage and spit them onto the page.
 * */
const BASIC_SAVES = {
    "twitchAccessToken": () => document.querySelector(`[name="at"]`).value,
    "ttsChannels": () => document.querySelector(`[name="connect"]`).value,
    "voiceOverrides": serializeVoiceOverrides,
    "soundRedeemsEnabled": () => document.querySelector(`[name="sound-redeems-enabled"]`).checked,
    "soundRedeems": serializeSoundRedeems,
}
function saveInputs() {
    for(let i in BASIC_SAVES) {
        localStorage.setItem(i, BASIC_SAVES[i]());
    }
}
const BASIC_LOADS = {
    '[name="at"]': () => {
        let params = new URLSearchParams(location.hash.slice(1));
        let givenToken = params.get("access_token");
        if(givenToken) return givenToken
        return localStorage.getItem(`twitchAccessToken`);
    },
    '[name="connect"]': () => localStorage.getItem(`ttsChannels`),
    '[name="sound-redeems-enabled"]': () => {
        return JSON.parse(localStorage.getItem(`soundRedeemsEnabled`))
    },
}
function loadInputs() {
    for(let i in BASIC_LOADS) {
        let node = document.querySelector(i);
        let value = BASIC_LOADS[i]();
        if(node.type.toLowerCase() == "checkbox") {
            node.checked = value;
        }
        else {
            node.value = value;
        }
    }

    // TTS voice overrides
    let voices = JSON.parse(localStorage.getItem(`voiceOverrides`));
    let voiceDom = document.querySelector("#voices");
    for(let vdo of voiceDom.children) {
        if(!vdo.classList.contains("template")) vdo.remove();
    }
    for(let u in voices) {
        addNewVoiceOverride(u, voices[u]);
    }

    // Sound redeems
    let sounds = JSON.parse(localStorage.getItem("soundRedeems"));
    if(sounds) {
        for(let name in sounds) {
            document.querySelector(`.sound[data-name="${name}"] input[name=managed]`).checked = sounds[name];
        }
    }
}


/**
 * Switch the username dropdown on a node to a text input.
 * */
function switchSelect(usernameHolder) {
    let input;
    let select = usernameHolder.querySelector("select");
    if(select === null) {
        let input = usernameHolder.querySelector("input");
        select = document.querySelector("#voices .template .username").cloneNode(true);
        select.value = input.value;
        usernameHolder.replaceChild(select, input);
    }
    else {
        input = document.createElement("input");
        input.classList.add("username");
        input.placeholder = "Twitch Username";
        input.onchange = saveInputs;
        input.value = select.value;
        usernameHolder.replaceChild(input, select);
    }
}


/**
 * Change all of the audio outputs for the page.
 * */
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


function expandItem(button) {
    let targets = document.querySelectorAll(button.dataset.target);
    let current = targets[0].dataset.hidden || "";
    for(let t of targets) {
        t.dataset.hidden = current == "" ? "1" : "";
    }
    // button.innerHTML = "\u2193"  // down arrow
    // button.innerHTML = "\u2191"  // up arrow
    button.innerHTML = current == "" ? "\u2193" : "\u2191";
}
