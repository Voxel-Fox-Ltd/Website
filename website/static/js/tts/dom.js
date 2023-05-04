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
        for(let v of VOICES) {
            let voiceOption = document.createElement("option");
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


/**
 * Load all of the inputs from localstorage and spit them onto the page.
 * */
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
 * Save all of the relevant inputs into localstorage.
 * */
function saveInputs() {
    localStorage.setItem(`twitchAccessToken`, document.querySelector(`[name="at"]`).value);
    localStorage.setItem(`ttsChannels`, document.querySelector(`[name="connect"]`).value);
    localStorage.setItem(`voiceOverrides`, serializeVoiceOverrides());
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
    let target = document.querySelector(button.dataset.target)
    let current = target.dataset.hidden || "0"
    if(current == "0") {
        target.dataset.hidden = "1";
        button.innerHTML = "\u2193"  // down arrow
    }
    else {
        target.dataset.hidden = "0";
        button.innerHTML = "\u2191"  // up arrow
    }
}
