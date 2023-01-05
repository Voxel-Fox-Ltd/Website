var stripe = Stripe("pk_live_0Fx3FqHVF6tDXipvuUxdSDeu00egEyOnyO");
var button = document.getElementById(document.currentScript.getattribute("button"));
button.onclick = () => {
    fetch("/webhooks/stripe/create_checkout_session", {
        method: "POST",
        body: JSON.stringify({
            product_name: document.currentScript.getattribute("name"),
            discord_user_id: document.currentScript.getattribute("user-id"),
            discord_guild_id: document.currentScript.getattribute("guild-id"),
        }),
    }).then(function (response) {
        return response.json();
    }).then(function (session) {
        return stripe.redirectToCheckout({ sessionId: session.id });
    }).then(function (result) {
        if (result.error) {
            alert(result.error.message);
        }
    }).catch(function (error) {
        console.error("Error:", error);
    });
};
