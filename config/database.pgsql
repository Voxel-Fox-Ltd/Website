CREATE TABLE IF NOT EXISTS guild_settings(
    guild_id BIGINT PRIMARY KEY,
    prefix VARCHAR(30)
);


CREATE TABLE IF NOT EXISTS user_settings(
    user_id BIGINT PRIMARY KEY
);


CREATE TABLE IF NOT EXISTS role_list(
    guild_id BIGINT,
    role_id BIGINT,
    key VARCHAR(50),
    value VARCHAR(50),
    PRIMARY KEY (guild_id, role_id, key)
);


CREATE TABLE IF NOT EXISTS channel_list(
    guild_id BIGINT,
    channel_id BIGINT,
    key VARCHAR(50),
    value VARCHAR(50),
    PRIMARY KEY (guild_id, channel_id, key)
);


CREATE TABLE IF NOT EXISTS paypal_purchases(
    id VARCHAR(64) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    customer_id VARCHAR(18),
    item_name VARCHAR(200) NOT NULL,
    option_selection VARCHAR(200),
    payment_amount INTEGER NOT NULL,
    payment_currency VARCHAR(10) NOT NULL,
    discord_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    custom TEXT,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    checkout_complete_timestamp TIMESTAMP,
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (id, transaction_type)
);


CREATE TABLE IF NOT EXISTS google_forms_redirects(
    form_id VARCHAR(100) NOT NULL,
    alias VARCHAR(100),
    username_field_id VARCHAR(100),
    user_id_field_id VARCHAR(100)
);
