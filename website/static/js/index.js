async function fetchBotCount() {
    site = await fetch("/bot_guild_count");
    data = await site.json();
    for(i of document.getElementsByClassName("guild-count")) {
        botName = i.dataset.botName.toLowerCase();
        if(data.hasOwnProperty(botName)) {
            i.innerHTML = `In ${parseInt(data[botName]).toLocaleString()} guilds`;
            i.style.display = "block";
        }
    }
}
