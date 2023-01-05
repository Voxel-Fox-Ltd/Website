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

    -- A Postgres connection string to connect to a database for some other BS
    external_dsn TEXT,
    -- SQL to run on successful payment and/or subscription create.
    success_sql TEXT,
    -- SQL to run on successful refund.
    refund_sql TEXT,
    -- SQL to run on cancelled subscription.
    cancel_sql TEXT,

    -- When this page is fetched, products from the same group will be shown
    -- together if there is one. If no group, then the product will not appear
    -- on a page.
    product_group TEXT,

    -- Whether or not the product is per guild (true) or per user (false). Only
    -- applies to purchases done through this site; not to externals.
    per_guild BOOLEAN NOT NULL DEFAULT FALSE,

    -- Text to be displayed on the portal page.
    description TEXT
);


CREATE TABLE IF NOT EXISTS transactions(
    timestamp TIMESTAMP,
    source TEXT NOT NULL,
    data JSON
);
