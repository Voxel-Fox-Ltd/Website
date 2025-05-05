/**
 * Functions and classes relating to the page DOM
 * */


/**
 * Add voices to a given dropdown.
 * */
function addVoicesToDropdown(dropdown) {
    let voiceOption = document.createElement("option");
    voiceOption.innerText = "";
    voiceOption.value = "";
    dropdown.appendChild(voiceOption);
    for(let v of VOICES) {
        voiceOption = document.createElement("option");
        voiceOption.innerText = v.display;
        voiceOption.value = v.name;
        dropdown.appendChild(voiceOption);
    }
}


/**
 * Add a new user voice override node to the list.
 * */
function addNewVoiceOverride(twitchUsername, voice) {

    let newVoice = document.createElement("tr");
    newVoice.classList.add("voice");
    newVoice.innerHTML = `
        <td>
            <input placeholder="Twitcher Username" class="username" onchange="javascript:saveInputs();" />
        </td>
        <td>
            <select
                class="voices"
                placeholder="Voice"
                onchange="javascript:saveInputs();">
            </select>
        </td>
        <td><button class="delete" onclick="javascript:deleteVoice(this)">Delete</button></td>`;
    if(twitchUsername !== null) newVoice.querySelector(`.username`).value = twitchUsername;
    addVoicesToDropdown(newVoice.querySelector(`.voices`));
    if(voice !== null) newVoice.querySelector(`.voices option[value="${voice}"]`).selected = true;
    let tbody = document.querySelector("#voice-table tbody");
    tbody.insertBefore(newVoice, tbody.firstElementChild);
}


/**
 * Serialize all of the voice override nodes into a JSON string.
 * */
function serializeVoiceOverrides() {
    let voices = document.querySelectorAll("#voice-table tbody tr");
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
    let voiceDom = document.querySelector("#voice-table tbody");
    voiceDom.innerHTML = "";
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
