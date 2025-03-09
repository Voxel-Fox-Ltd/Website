/**
 * Functions and classes relating to the main running of the page.
 * */


const CLIENT_ID = "eatw6619xc67g5udj97dmx096vyxb7";


var irc = null;
var pubsub = null;
async function connectTTS() {
    if(irc === null || pubsub === null) {
        saveInputs();
        document.querySelector(`[name="connect"]`).disabled = true;
        document.querySelector(`#login-button`).disabled = true;
        let accessToken = document.querySelector(`[name="at"]`).value.trim();
        let connectChannels = document.querySelector(`[name="connect"]`).value.trim().split("\n");
        if(irc === null) {
            irc = new TwitchIRC(accessToken, connectChannels);
            await irc.connect();
            if(irc.socket === null) {
                irc = null;
                alert("Failed to connect to Twitch via IRC.")
            }
        }
        if(pubsub === null) {
            pubsub = new TwitchPubSub(accessToken, irc.userId, CLIENT_ID);
            pubsub.connect();
            for(let b of document.querySelectorAll("#modify-all-point-rewards button")) b.disabled = false;
        }
    }
    else {
        irc.close();
        pubsub.close();
        document.querySelector(`[name="connect"]`).disabled = false;
        document.querySelector(`#login-button`).disabled = false;
        for(let b of document.querySelectorAll("#modify-all-point-rewards button")) b.disabled = true;
        irc = null;
        pubsub = null;
    }
    document.querySelector("#tts-connect").innerHTML = (
        irc === null ? "Connect Twitch" : "Disconnect Twitch"
    );
}


function redirectToLogin() {
    let params = {
        "client_id": CLIENT_ID,
        "redirect_uri": "https://voxelfox.co.uk/tts",
        "response_type": "token",
        "scope": "openid chat:read channel:manage:redemptions",
        "claims": JSON.stringify({"userinfo": {"preferred_username": null}}),
    }
    let usp = new URLSearchParams(params);
    window.location.href = (
        `https://id.twitch.tv/oauth2/authorize?`
        + usp.toString()
    );
}


async function modifyAllRewards(enable) {
    if(pubsub === null) return;
    for(let i of document.querySelectorAll("#modify-all-point-rewards button")) i.disabled = true;
    for(let i of document.querySelectorAll(".sound")) {
        if(i.dataset.id == "" || i.dataset.id === null) continue;
        r = new PointsReward({
            id: i.dataset.id,
            broadcaster_id: pubsub.userId,
        });
        if(!i.querySelector("input[name=managed]").checked) continue;
        if(enable) {
            await r.enable(pubsub.clientId, pubsub.token)
        }
        else {
            await r.disable(pubsub.clientId, pubsub.token)
        }
    }
    for(let i of document.querySelectorAll("#modify-all-point-rewards button")) i.disabled = false;
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
