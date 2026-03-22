CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE cities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE districts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    city_id INT NOT NULL,
    CONSTRAINT fk_city
        FOREIGN KEY (city_id) REFERENCES cities(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE transports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    number VARCHAR(20) NOT NULL UNIQUE,
    capacity INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE courier_profiles (
    user_id INT PRIMARY KEY,
    transport_id INT NULL,
    device_info VARCHAR(255) NULL,
    CONSTRAINT fk_courier_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT fk_courier_transport
        FOREIGN KEY (transport_id) REFERENCES transports(id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

CREATE TABLE courier_districts (
    courier_id INT NOT NULL,
    district_id INT NOT NULL,
    PRIMARY KEY (courier_id, district_id),
    CONSTRAINT fk_cd_courier
        FOREIGN KEY (courier_id) REFERENCES courier_profiles(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT fk_cd_district
        FOREIGN KEY (district_id) REFERENCES districts(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE warehouses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE warehouse_addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id INT NOT NULL,
    address_line TEXT NOT NULL,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE
);

CREATE TABLE warehouse_phones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id INT NOT NULL,
    phone VARCHAR(30) NOT NULL,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE
);

CREATE TABLE counterparties (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE counterparty_addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    counterparty_id INT NOT NULL,
    address_line TEXT NOT NULL,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id) ON DELETE CASCADE
);

CREATE TABLE counterparty_phones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    counterparty_id INT NOT NULL,
    phone VARCHAR(30) NOT NULL,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id) ON DELETE CASCADE
);

CREATE TABLE price_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    price_type_id INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (price_type_id) REFERENCES price_types(id)
);

CREATE TABLE client_phones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    phone VARCHAR(20) NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE TABLE client_addresses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    city_id INT NOT NULL,
    district_id INT NOT NULL,
    address_line TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (city_id) REFERENCES cities(id),
    FOREIGN KEY (district_id) REFERENCES districts(id)
);

CREATE TABLE client_block_reasons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    reason TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE TABLE locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- warehouse, courier, counterparty, client
    user_id INT NULL,
    warehouse_id INT NULL,
    counterparty_id INT NULL,
    client_id INT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE product_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE brands (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    product_type_id INT NOT NULL,
    brand_id INT NOT NULL,
    volume VARCHAR(100) NULL,
    quantity_per_block INT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (product_type_id) REFERENCES product_types(id),
    FOREIGN KEY (brand_id) REFERENCES brands(id)
);

CREATE TABLE product_states (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE services (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE service_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service_id INT NOT NULL,
    product_id INT NOT NULL,
    service_type VARCHAR(50) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE service_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service_id INT NOT NULL,
    city_id INT NOT NULL,
    price_type_id INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (city_id) REFERENCES cities(id),
    FOREIGN KEY (price_type_id) REFERENCES price_types(id)
);

CREATE TABLE stocks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    location_id INT NOT NULL,
    product_id INT NOT NULL,
    product_state_id INT NOT NULL,
    quantity FLOAT NOT NULL DEFAULT 0.0,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (product_state_id) REFERENCES product_states(id),
    UNIQUE KEY uq_stock_location_product_state (location_id, product_id, product_state_id)
);

CREATE TABLE transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operation_type VARCHAR(50) NOT NULL,
    from_location_id INT NULL,
    to_location_id INT NULL,
    product_id INT NOT NULL,
    product_state_id INT NOT NULL,
    quantity FLOAT NOT NULL,
    user_id INT NULL,
    note TEXT NULL,
    FOREIGN KEY (from_location_id) REFERENCES locations(id),
    FOREIGN KEY (to_location_id) REFERENCES locations(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (product_state_id) REFERENCES product_states(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE discounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    discount_type VARCHAR(50) NOT NULL,
    value DECIMAL(10,2) NULL,
    limit_count INT NULL,
    usage_count INT NOT NULL DEFAULT 0,
    nth_order INT NULL,
    start_date DATE NULL,
    end_date DATE NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    is_combinable BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE discount_services (
    discount_id INT NOT NULL,
    service_id INT NOT NULL,
    PRIMARY KEY (discount_id, service_id),
    FOREIGN KEY (discount_id) REFERENCES discounts(id),
    FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE TABLE discount_cities (
    discount_id INT NOT NULL,
    city_id INT NOT NULL,
    PRIMARY KEY (discount_id, city_id),
    FOREIGN KEY (discount_id) REFERENCES discounts(id),
    FOREIGN KEY (city_id) REFERENCES cities(id)
);

CREATE TABLE discount_price_types (
    discount_id INT NOT NULL,
    price_type_id INT NOT NULL,
    PRIMARY KEY (discount_id, price_type_id),
    FOREIGN KEY (discount_id) REFERENCES discounts(id) ON DELETE CASCADE,
    FOREIGN KEY (price_type_id) REFERENCES price_types(id) ON DELETE CASCADE
);

CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    client_id INT NOT NULL,
    client_address_id INT NOT NULL,
    client_phone_id INT NOT NULL,
    courier_id INT NULL,
    user_id INT NOT NULL,
    
    note TEXT NULL,
    
    delivery_date DATE NOT NULL,
    delivery_time_type VARCHAR(50) NOT NULL,
    delivery_time TIME NULL,
    
    payment_type VARCHAR(50) NOT NULL,
    
    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    cash_amount DECIMAL(12,2) NULL,
    card_amount DECIMAL(12,2) NULL,
    
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    FOREIGN KEY (client_address_id) REFERENCES client_addresses(id) ON DELETE RESTRICT,
    FOREIGN KEY (client_phone_id) REFERENCES client_phones(id) ON DELETE RESTRICT,
    FOREIGN KEY (courier_id) REFERENCES courier_profiles(user_id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    service_id INT NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    price DECIMAL(10,2) NULL,
    total_price DECIMAL(10,2) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT
);

CREATE TABLE order_discounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    discount_id INT NOT NULL,
    discount_amount DECIMAL(10,2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (discount_id) REFERENCES discounts(id) ON DELETE CASCADE
);

CREATE TABLE client_credits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL UNIQUE,
    credit_limit DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    used_credit DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
);

CREATE TABLE credit_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_credit_id INT NOT NULL,
    order_id INT NULL,
    payment_type VARCHAR(50) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    description TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (client_credit_id) REFERENCES client_credits(id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

ALTER TABLE service_rules ADD COLUMN product_state_id INT NOT NULL AFTER product_id;
ALTER TABLE service_rules ADD CONSTRAINT fk_sr_product_state FOREIGN KEY (product_state_id) REFERENCES product_states(id);

CREATE TABLE courier_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    courier_id INT NOT NULL,
    order_id INT NOT NULL UNIQUE,
    payment_type VARCHAR(50) NOT NULL, -- тип оплаты по итогу (cash, card, cash_and_card)
    cash_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    card_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    is_handed_over BOOLEAN NOT NULL DEFAULT FALSE,
    handed_over_at DATETIME NULL,
    accounter_id INT NULL,
    accounter_note TEXT NULL,
    
    FOREIGN KEY (courier_id) REFERENCES courier_profiles(user_id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (accounter_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE sms_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    recipient_phone VARCHAR(50) NOT NULL,
    message_text TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);
