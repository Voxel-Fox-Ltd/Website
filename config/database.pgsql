CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


CREATE TABLE IF NOT EXISTS guild_settings(
    guild_id BIGINT PRIMARY KEY,
    prefix VARCHAR(30)
);


CREATE TABLE IF NOT EXISTS user_settings(
    user_id BIGINT PRIMARY KEY
);


CREATE TABLE IF NOT EXISTS google_forms_redirects(
    form_id VARCHAR(100) NOT NULL,
    alias VARCHAR(100),
    username_field_id VARCHAR(100),
    user_id_field_id VARCHAR(100)
);


CREATE TABLE IF NOT EXISTS checkout_items(
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    product_name TEXT PRIMARY KEY,
    success_url TEXT NOT NULL DEFAULT 'http://localhost',
    cancel_url TEXT NOT NULL DEFAULT 'http://localhost',
    subscription BOOLEAN NOT NULL DEFAULT FALSE,

    stripe_product_id TEXT NOT NULL,
    stripe_price_id TEXT NOT NULL,
    paypal_plan_id TEXT,

    transaction_webhook TEXT,
    transaction_webhook_authorization TEXT NOT NULL DEFAULT '',

    -- When this page is fetched, products from the same group will be shown
    -- together if there is one. If no group, then the product will not appear
    -- on a page.
    product_group TEXT,

    -- Whether or not the product is per guild (true) or per user (false). Only
    -- applies to purchases done through this site; not to externals.
    per_guild BOOLEAN NOT NULL DEFAULT FALSE,

    -- Whether or not the product can be purchased multiple times. Ignored if
    -- the product is a subscription.
    multiple BOOLEAN NOT NULL DEFAULT FALSE,

    -- Text to be displayed on the portal page.
    description TEXT
);


CREATE TABLE IF NOT EXISTS transactions(
    timestamp TIMESTAMP,
    source TEXT NOT NULL,
    data JSON
);
-- This table is just a transaction log


CREATE TABLE IF NOT EXISTS purchases(
    id UUID NOT NULL DEFAULT uuid_generate_v4(),  -- ID of the purchase; internal reference only
    user_id BIGINT NOT NULL,  -- user who purchased the item
    product_name TEXT NOT NULL,  -- the item the purchased
    guild_id BIGINT,  -- the guild the item was purchased for, if any
    expiry_time TIMESTAMP,  -- if the item is a subscription, when it expires (if expiring)
    cancel_url TEXT,  -- if the item is a subscription, the URL to cancel it
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);