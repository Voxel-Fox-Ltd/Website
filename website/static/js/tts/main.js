/**
 * Functions and classes relating to the main running of the page.
 * */

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
