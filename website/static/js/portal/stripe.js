var stripe = Stripe("pk_live_0Fx3FqHVF6tDXipvuUxdSDeu00egEyOnyO");
var button = document.getElementById(document.currentScript.getAttribute("button"));
button.onclick = () => {
    fetch("/webhooks/stripe/create_checkout_session", {
        method: "POST",
        body: JSON.stringify({
            product_name: document.currentScript.getAttribute("name"),
            discord_user_id: document.currentScript.getAttribute("user-id"),
            discord_guild_id: document.currentScript.getAttribute("guild-id"),
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
