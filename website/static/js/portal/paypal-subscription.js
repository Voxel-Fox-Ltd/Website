paypal.Buttons({
    style: {
        label: 'subscribe',
        color: 'gold',
        tagline: false,
        layout: 'horizontal',
    },
   createSubscription: function(data, actions) {
        return actions.subscription.create({
           'plan_id': document.currentScript.getattribute("plan-id"),
           'custom_id': JSON.stringify({
                discord_user_id: document.currentScript.getattribute("user-id"),
                discord_guild_id: document.currentScript.getattribute("guild-id"),
            }),
        });
    },
    onApprove: function(data, actions) {
        alert(data.subscriptionID);
    }
}).render(document.currentScript.getattribute("button"));
