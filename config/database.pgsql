CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";


CREATE TABLE IF NOT EXISTS google_forms_redirects(
    form_id VARCHAR(100) NOT NULL,
    alias VARCHAR(100),
    username_field_id VARCHAR(100),
    user_id_field_id VARCHAR(100)
);


-- A table of users (and related information) who can create and manage
-- checkout items
CREATE TABLE IF NOT EXISTS payment_users(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    login_id UUID NOT NULL REFERENCES login_users(id),
    manager BOOLEAN NOT NULL DEFAULT FALSE,
    stripe_id TEXT,
    paypal_id TEXT,
    paypal_client_id TEXT,
    paypal_client_secret TEXT
);


CREATE TABLE IF NOT EXISTS login_users(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    discord_user_id TEXT UNIQUE,
    discord_refresh_token TEXT,
    google_user_id TEXT UNIQUE,
    google_refresh_token TEXT,
    facebook_user_id TEXT UNIQUE,
    facebook_refresh_token TEXT,
    everlasting_user_id TEXT UNIQUE,
    everlasting_refresh_token TEXT  -- Will never be used, but dw about it
);


CREATE TABLE IF NOT EXISTS checkout_items(
    id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
    creator_id UUID NOT NULL REFERENCES payment_users(id),

    -- Product information
    product_name CITEXT NOT NULL,
    subscription BOOLEAN NOT NULL DEFAULT FALSE,
    success_url TEXT NOT NULL DEFAULT 'https://voxelfox.co.uk',
    cancel_url TEXT NOT NULL DEFAULT 'https://voxelfox.co.uk',
    required_logins INTEGER NOT NULL DEFAULT 0,

    -- Information on the product IDs
    stripe_product_id TEXT NOT NULL,
    stripe_price_id TEXT NOT NULL,
    paypal_plan_id TEXT,

    -- Webhooks to send to when there's a purchase been made
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
    description TEXT,

    -- Quantities for the items.
    quantity INTEGER NOT NULL DEFAULT 1,
    min_quantity INTEGER,
    max_quantity INTEGER,
    base_product UUID REFERENCES checkout_items(id) ON DELETE SET NULL,

    -- Add our constraints
    UNIQUE (creator_id, product_name)
);


-- A transaction log for purchases made through the website. Doesn't check
-- validity, but rather just a log of income.
CREATE TABLE IF NOT EXISTS transactions(
    id UUID NOT NULL DEFAULT uuid_generate_v4(),

    -- The item that was purchased
    product_id UUID NOT NULL REFERENCES checkout_items(id),

    -- The amount of the purchase
    amount_gross INTEGER NOT NULL,
    amount_net INTEGER,
    currency VARCHAR(3) NOT NULL,

    -- The amount that actually goes into the user's account
    settle_amount INTEGER NOT NULL,
    settle_currency VARCHAR(3) NOT NULL,

    -- The transaction ID from the payment processor
    identifier TEXT NOT NULL,

    -- The payment processor that was used
    payment_processor TEXT NOT NULL,

    -- Timestamp of purchase
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Information about the purchase and the purchaser
    customer_email CITEXT,
    metadata TEXT
);


-- A table holding references to the products that a user has purchased.
-- Only contains ACTIVE purchases - non-refunded purchases, active
-- subscriptions, etc. This table should not be used as a reference for
-- income.
CREATE TABLE IF NOT EXISTS purchases(
    id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
    quantity INTEGER NOT NULL DEFAULT 1,
    identifier TEXT UNIQUE DEFAULT uuid_generate_v4()::TEXT,  -- identifier from the API

    -- The product that was purchased
    product_id UUID NOT NULL REFERENCES checkout_items(id),

    -- The user who purchased the item
    user_id UUID,  -- technically not null, but I can't promise everyone has an account
    discord_user_id BIGINT,
    discord_guild_id BIGINT,

    -- If the item is a subscription, cancel metadata
    cancel_url TEXT,
    expiry_time TIMESTAMP,  -- If cancelled, when the subscription expires

    -- Timestamp of purchase
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- Create some indexes for easier searching
CREATE INDEX IF NOT EXISTS
    purchases_user_id_product_name_expiry_time_idx
    ON purchases
    (user_id, product_id, expiry_time);
CREATE INDEX IF NOT EXISTS
    purchases_guild_id_product_name_expiry_time_idx
    ON purchases
    (guild_id, product_id, expiry_time);
