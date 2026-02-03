/**
 * Functions and classes relating to the page DOM
 * */


/**
 * Add voices to a given dropdown.
 * */
function addVoicesToDropdown(dropdown) {

    // Group voices by their accent
    let voiceGroups = {};
    for(let v of VOICES) {
        let group = v.groupName;
        if(!(group in voiceGroups)) {
            voiceGroups[group] = [];
        }
        voiceGroups[group].push(v);
    }

    // Add the voices to the dropdown
    for(let groupName in voiceGroups) {
        let optgroup = document.createElement("optgroup");
        optgroup.label = groupName;
        for(let v of voiceGroups[groupName]) {
            let voiceOption = document.createElement("option");
            voiceOption.innerText = v.display;
            voiceOption.value = v.name;
            optgroup.appendChild(voiceOption);
        }
        dropdown.appendChild(optgroup);
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
            <input placeholder="Twitch Username" class="username" onchange="javascript:saveInputs();" />
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
    if(voice !== null) {
        try {
            newVoice.querySelector(`.voices option[value="${voice}"]`).selected = true;
        }
        catch(e) {
            console.warn(`Voice ${voice} not found for user ${twitchUsername}`);
        }
    }
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
        if(user == "") continue;
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
    "awsAccessKey": () => document.querySelector(`[name="pak"]`).value,
    "awsSecretKey": () => document.querySelector(`[name="psk"]`).value,
    "ttsChannels": () => document.querySelector(`[name="connect"]`).value,
    "voiceOverrides": serializeVoiceOverrides,
    "soundRedeemsEnabled": () => document.querySelector(`[name="sound-redeems-enabled"]`).checked,
    "soundRedeems": serializeSoundRedeems,
    "outputType": () => document.querySelector(`[name="output-type"]:checked`).value,
    "outputUserType": () => {
        let output = 0;
        for(let i of document.querySelectorAll(`.output-user-type-checkbox:checked`)) {
            output |= parseInt(i.value);
        }
        return output;
    }
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
    '[name="pak"]': () => localStorage.getItem(`awsAccessKey`),
    '[name="psk"]': () => localStorage.getItem(`awsSecretKey`),
    '[name="sound-redeems-enabled"]': () => {
        return JSON.parse(localStorage.getItem(`soundRedeemsEnabled`))
    },
    '[name="output-type"]': () => localStorage.getItem("outputType"),
}
function loadInputs() {
    for(let i in BASIC_LOADS) {
        let node = document.querySelector(i);
        let value = BASIC_LOADS[i]();
        if(node.type.toLowerCase() == "checkbox") {
            node.checked = value;
        }
        else if(node.type.toLowerCase() == "radio") {
            let radios = document.querySelectorAll(`${i}`);
            for(let r of radios) {
                r.checked = false;
                if(r.value == value) {
                    r.checked = true;
                }
            }
        }
        else {
            node.value = value;
        }
    }

    // TTS voice overrides
    let voices = JSON.parse(localStorage.getItem(`voiceOverrides`));
    let voiceDom = document.querySelector("#voice-table tbody");
    voiceDom.innerHTML = "";
    let sortedKeys = (
        Object.keys(voices)
        .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
        .reverse()
    );
    for(let u of sortedKeys) {
        addNewVoiceOverride(u, voices[u]);
    }

    // Sound redeems
    let sounds = JSON.parse(localStorage.getItem("soundRedeems"));
    if(sounds) {
        for(let name in sounds) {
            document.querySelector(`.sound[data-name="${name}"] input[name=managed]`).checked = sounds[name];
        }
    }

    // Output type
    let outputType = parseInt(localStorage.getItem("outputUserType"));
    let checkboxes = document.querySelectorAll(`.output-user-type-checkbox`);
    for(let i of checkboxes) {
        i.checked = false;
        if(outputType & parseInt(i.value)) {
            i.checked = true;
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
