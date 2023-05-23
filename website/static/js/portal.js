function guildSelectChange(itemId) {
  var guildSelect = document.querySelector(`.item[data-id="${itemId}"] .guild-select`);
  var guildId = guildSelect.value;
  if (!guildId) {
    return;
  }
  window.location.href = `/portal/item/${itemId}?guild=${guildId}`;
}


async function getGuilds() {

  // Get selectors
  let allGuildSelectors = document.querySelectorAll(".guild-select");
  if(allGuildSelectors.length <= 0) return;

  // See if we need to replace the item
  if (document.querySelector("#guild-script").dataset.loggedIn == "0") {
    for(let g of allGuildSelectors) {
      g.outerHTML = `<a href="?login" class="button">Login to see guilds</a>`;
    }
    return;
  }

  // Get guilds
  var guilds = await fetch("/api/portal/get_guilds");
  guilds = await guilds.json();

  // Sort by name
  guilds.sort((a, b) => {
    var nameA = a.name.toUpperCase();
    var nameB = b.name.toUpperCase();
    if (nameA < nameB) {
      return -1;
    }
    if (nameA > nameB) {
      return 1;
    }
    return parseInt(a.id) - parseInt(b.id);
  });

  // Add to dropdowns
  for(let select of allGuildSelectors) {
    select.innerHTML = "<option value='' selected>Purchase for Guild</option>";
    let owned = document.createElement("optgroup");
    owned.label = "Guilds you own";
    let administrate = document.createElement("optgroup");
    administrate.label = "Guilds you administrate";
    let manage = document.createElement("optgroup");
    manage.label = "Guilds you manage";
    let contained = document.createElement("optgroup");
    contained.label = "Guilds you're in";
    for(let guild of guilds) {
      let option = document.createElement("option");
      option.value = guild.id;
      option.innerText = guild.name;
      if(guild.permissions.owner) {
        owned.appendChild(option);
      } else if(guild.permissions.administrator) {
        administrate.appendChild(option);
      } else if(guild.permissions.manage_guild) {
        manage.appendChild(option);
      } else {
        contained.appendChild(option);
      }
    }
    select.appendChild(owned);
    select.appendChild(administrate);
    select.appendChild(manage);
    select.appendChild(contained);
  }
}
getGuilds();
