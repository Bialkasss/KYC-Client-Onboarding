-- ----------------------------------------------------------------------------
-- 00_create_database_and_schema.sql
-- Recreates the KYC database and schema from scratch.
-- ----------------------------------------------------------------------------

DROP DATABASE IF EXISTS `kyc_db`;
CREATE DATABASE `kyc_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `kyc_db`;

SET FOREIGN_KEY_CHECKS = 0;

-- 1. Compliance Officers
CREATE TABLE `compliance_officer` (
    `officer_id` INT AUTO_INCREMENT PRIMARY KEY,
    `full_name` VARCHAR(255) NOT NULL,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Admin Officers
CREATE TABLE `admin_officer` (
    `admin_id` INT AUTO_INCREMENT PRIMARY KEY,
    `full_name` VARCHAR(255) NOT NULL,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'PBKDF2-HMAC-SHA256 salted hash, see util.PasswordHasher',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 3. Document Types
CREATE TABLE `document_type` (
    `doc_type_id` INT AUTO_INCREMENT PRIMARY KEY,
    `doc_type_name` VARCHAR(100) NOT NULL COMMENT 'PASSPORT, DRIVING_LICENCE, NATIONAL_ID, UTILITY_BILL, BANK_STATEMENT, COUNCIL_TAX_BILL, KYC_APPLICATION_FORM, TAX_SELF_CERT_FATCA_CRS, PAY_SLIP_TAX_RETURN, SHARE_PURCHASE_AGREEMENT, PROBATE_WILL, DEED_OF_SALE, ACCOUNTANT_NET_ASSET_DECLARATION, OFFICIAL_GOVT_APPOINTMENT_LETTER, PEP_BUSINESS_RATIONALE_STMT, CERTIFICATE_OF_INCORPORATION, MEMORANDUM_ARTICLES_ASSOCIATION, COMMERCIAL_REGISTER_EXTRACT, CERTIFICATE_OF_GOOD_STANDING, CORPORATE_GROUP_OWNERSHIP_CHART, UBO_DECLARATION_FORM, BOARD_RESOLUTION_ACCOUNT_OPENING, AUTHORIZED_SIGNATORY_LIST, AUDITED_FINANCIAL_STATEMENTS, TRUST_DEED, DEED_OF_VARIATION, LETTER_OF_WISHES',
    `required_for_individual` BOOLEAN NOT NULL,
    `required_for_corporate` BOOLEAN NOT NULL,
    `required_for_trust` BOOLEAN NOT NULL ,
    `required_for_political` BOOLEAN NOT NULL 
) ENGINE=InnoDB;

-- 4. Clients
CREATE TABLE `client` (
    `client_id` INT AUTO_INCREMENT PRIMARY KEY,
    `full_name` VARCHAR(255) NOT NULL,
    `client_type` VARCHAR(50) NOT NULL COMMENT 'INDIVIDUAL / CORPORATE / TRUST / POLITICAL',
    `nationality` CHAR(2) NOT NULL,
    `date_of_birth` DATE NOT NULL,
    `country_of_birth` CHAR(2) NOT NULL,
    `tax_residency` CHAR(2) NOT NULL,
    `occupation` VARCHAR(80) NULL,
    `employer` VARCHAR(80) NULL,
    `main_source_of_funds` VARCHAR(80),
    `annual_income_band` VARCHAR(80) COMMENT '<25K / 25-50K  / 50-100K / 100-250K / 250K+',
    `status` VARCHAR(50) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING / APPROVED / SUSPENDED / REJECTED',
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL COMMENT 'PBKDF2-HMAC-SHA256 salted hash, see util.PasswordHasher',
    `is_pep` BOOLEAN NOT NULL DEFAULT FALSE,
    `adverse_media_hits` INT NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 5. Client Addresses
CREATE TABLE `client_address` (
    `address_id` INT AUTO_INCREMENT PRIMARY KEY,
    `client_id` INT NOT NULL,
    `address_type` VARCHAR(50) NOT NULL DEFAULT 'REGISTERED' COMMENT 'REGISTERED / MAILING ',
    `line1` VARCHAR(255) NOT NULL,
    `line2` VARCHAR(255),
    `city` VARCHAR(100) NOT NULL,
    `country` CHAR(2) NOT NULL,
    `state` varchar(255),
    `postcode` VARCHAR(20) NOT NULL,
    `is_current` VARCHAR(10) NOT NULL DEFAULT 'TRUE',
    FOREIGN KEY (`client_id`) REFERENCES `client` (`client_id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 6. Onboarding Cases
CREATE TABLE `onboarding_case` (
    `case_id` INT AUTO_INCREMENT PRIMARY KEY,
    `client_id` INT NOT NULL,
    `opened_date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `product_type` VARCHAR(50) NOT NULL,
    `case_status` VARCHAR(20) NOT NULL DEFAULT 'OPEN' COMMENT 'OPEN / PENDING / CLOSED',
    `assigned_officer_id` INT NULL,
    `due_date` DATE NULL,
    `completed_date` TIMESTAMP NULL DEFAULT NULL,
    `rejection_reason` VARCHAR(255) NULL,
    `jurisdiction_risk` VARCHAR(20) DEFAULT 'LOW' COMMENT 'LOW / MEDIUM / HIGH',
    `ml_prediction` VARCHAR(20) NULL COMMENT 'APPROVED / REJECTED, predicted by ML model',
    `ml_approval_probability` DECIMAL(5,4) NULL COMMENT 'Predicted probability of approval, 0-1',
    `ml_recommendations` TEXT NULL COMMENT 'JSON array of DiCE counterfactual suggestions; only populated when ml_prediction = REJECTED',
    `ml_predicted_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'When the prediction was last (re)computed',
    FOREIGN KEY (`client_id`) REFERENCES `client` (`client_id`) ON DELETE CASCADE,
    FOREIGN KEY (`assigned_officer_id`) REFERENCES `compliance_officer` (`officer_id`) ON DELETE SET NULL,
    INDEX `idx_onboarding_case_ml_prediction` (`ml_prediction`)
) ENGINE=InnoDB;

-- 7. Documents
CREATE TABLE `document` (
    `doc_id` INT AUTO_INCREMENT PRIMARY KEY,
    `case_id` INT NOT NULL,
    `doc_type_id` INT NOT NULL,
    `submission_date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `verified_flag` BOOLEAN NOT NULL DEFAULT FALSE,
    `verified_by` INT NULL,
    `verified_at` TIMESTAMP NULL DEFAULT NULL,
    `expiry_date` DATE NULL,
    `rejection_reason` VARCHAR(255) NULL,
    FOREIGN KEY (`case_id`) REFERENCES `onboarding_case` (`case_id`) ON DELETE CASCADE,
    FOREIGN KEY (`doc_type_id`) REFERENCES `document_type` (`doc_type_id`) ON DELETE RESTRICT,
    FOREIGN KEY (`verified_by`) REFERENCES `compliance_officer` (`officer_id`) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 8. Risk Classifications
CREATE TABLE `risk_classification` (
    `classification_id` INT AUTO_INCREMENT PRIMARY KEY,
    `case_id` INT NOT NULL,
    `risk_level` VARCHAR(20) NOT NULL COMMENT 'LOW / MEDIUM / HIGH',
    `classification_date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `assessed_by` INT NULL,
    `rationale` TEXT NULL,
    `next_review_date` DATE NULL,
    FOREIGN KEY (`case_id`) REFERENCES `onboarding_case` (`case_id`) ON DELETE CASCADE,
    FOREIGN KEY (`assessed_by`) REFERENCES `compliance_officer` (`officer_id`) ON DELETE SET NULL
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;