paypal.Buttons({
    style: {
        label: 'subscribe',
        color: 'gold',
        tagline: false,
        layout: 'horizontal',
    },
   createSubscription: function(data, actions) {
        return actions.subscription.create({
           'plan_id': document.currentScript.getAttribute("plan-id"),
           'custom_id': JSON.stringify({
                discord_user_id: document.currentScript.getAttribute("user-id"),
                discord_guild_id: document.currentScript.getAttribute("guild-id"),
            }),
        });
    },
    onApprove: function(data, actions) {
        alert(data.subscriptionID);
    }
}).render("#" + document.currentScript.getAttribute("button"));
